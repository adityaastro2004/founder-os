#!/usr/bin/env bash
# Guarded manual Vercel production deploy for the Founder OS web app.
#
# Normally you do NOT need this: the Vercel project is git-integrated, so a
# merge to main cloud-builds and takes the production alias automatically,
# using the dashboard env vars. Use this script only when a manual prebuilt
# prod deploy is genuinely required (e.g. a new NEXT_PUBLIC_* var must go
# live before a merge lands — add it with `vercel env add` first so cloud
# builds keep it too).
#
# Why the guards exist: on 2026-07-21 a manual `vercel build --prod` +
# `deploy --prebuilt --prod` was run from the shared root checkout while it
# sat on an old feature branch, and it silently reverted production to
# pre-revamp code minutes after the git integration had deployed the real
# thing. Manual prod deploys must be impossible from a stale or dirty tree.
#
# Usage: ./scripts/deploy-web.sh    (from the git root of any clean worktree)
#
# Refuses to run unless HEAD == origin/main (after a fresh fetch) and the
# working tree is completely clean. Builds from the GIT root — the Vercel
# project's rootDirectory is founder-os/apps/web relative to the git root,
# and `vercel deploy --prebuilt` only ships <cwd>/.vercel/output. Deploys
# are tagged (-m gitSha=…) so `vercel inspect` shows provenance.
set -euo pipefail

die() { echo "deploy-web: $*" >&2; exit 1; }

ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"

git fetch -q origin main

HEAD_SHA=$(git rev-parse HEAD)
[ "$HEAD_SHA" = "$(git rev-parse origin/main)" ] ||
  die "HEAD ($(git rev-parse --short HEAD)) != origin/main ($(git rev-parse --short origin/main)).
Production deploys only from origin/main — use a clean worktree:
  git worktree add /tmp/fos-deploy origin/main && cd /tmp/fos-deploy && ./scripts/deploy-web.sh"

# .vercel/ is this script's own workspace (link + pulled env + build output) and
# is not yet gitignored on main — tolerate it, and nothing else.
DIRTY=$(git status --porcelain | grep -v '^?? \.vercel/' || true)
[ -z "$DIRTY" ] ||
  die "working tree is not clean — deploy only from a pristine checkout of origin/main:
$DIRTY"

# The monorepo needs its workspace deps for `vercel build`.
[ -d "$ROOT/founder-os/node_modules" ] || (cd "$ROOT/founder-os" && npm install)

# Link the project at the git root if this worktree never deployed. The
# rootDirectory setting matters: `vercel build` trusts the on-disk copy, and
# without it the build looks in the wrong directory. IDs are not secrets.
if [ ! -f .vercel/project.json ]; then
  mkdir -p .vercel
  cat > .vercel/project.json <<'EOF'
{
  "projectId": "prj_FMSzIW4dJNzu7SIDTOEEYqeOl9DI",
  "orgId": "team_GWqWCsrkcqhpVUca2n0LaRmf",
  "projectName": "web",
  "settings": { "framework": "nextjs", "rootDirectory": "founder-os/apps/web", "nodeVersion": "24.x" }
}
EOF
fi

rm -rf .vercel/output
vercel pull --yes --environment=production
vercel build --prod --yes

# Bundle sanity (2026-07-11 incident: localhost API URL baked into prod).
! grep -rq "localhost:8000" .vercel/output/static ||
  die "built bundle contains localhost:8000 — NEXT_PUBLIC_API_URL is wrong, refusing to deploy"
grep -rq "pk_live\|pk_test" .vercel/output/static ||
  die "built bundle has no Clerk publishable key — env pull incomplete, refusing to deploy"

vercel deploy --prebuilt --prod --yes -m gitSha="$HEAD_SHA"

echo
echo "deploy-web: deployed origin/main @ $HEAD_SHA to production"
curl -fsS -o /dev/null -w "deploy-web: https://myfounder.vercel.app -> %{http_code}\n" https://myfounder.vercel.app/
