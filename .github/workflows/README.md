# CI/CD — GitHub Actions

This repo is **double-nested**: the git root holds these workflows; the Turborepo
monorepo lives in [`founder-os/`](../../founder-os). Paths in the workflows reflect
that (frontend → `founder-os/`, backend → `founder-os/apps/api`).

## Workflows

| File | Trigger | What it does |
|------|---------|--------------|
| [`ci.yml`](ci.yml) | push/PR to `main`, manual | The main gate (below). |
| [`codeql.yml`](codeql.yml) | push/PR to `main`, weekly cron | CodeQL static security analysis for Python + JS/TS (`security-and-quality` query suite). |
| [`dependency-review.yml`](dependency-review.yml) | PR to `main` | Fails a PR that introduces a dependency with a **high+** known vulnerability; comments a summary. |
| [`deploy.yml`](deploy.yml) | after **CI** passes on `main`, manual | SSHes into the VPS/EC2 host and runs `docker compose -f docker-compose.prod.yml up -d --build`. Needs `DEPLOY_*` secrets (see [`../../DEPLOY.md`](../../DEPLOY.md) Part 4). Frontend deploys on Vercel separately. |

## `ci.yml` jobs

- **frontend** — `npm ci` → `npm run lint` → `npm run check-types` → `npm run build`
  across the Turborepo (web + docs + packages). Node 22, npm + Turbo caches.
  Dummy `NEXT_PUBLIC_*` / Clerk / Stripe values are injected so the build doesn't
  fail on missing public keys — they are **not** real credentials.
- **backend** — Python 3.14 against a `pgvector/pgvector:pg16` Postgres + Redis 7
  service:
  - `ruff check --select=E9,F63,F7,F82 --ignore=F821` (blocking: syntax errors +
    real pyflakes bugs; F821 excluded — the code uses string forward-ref type
    hints the import smoke test validates instead),
  - full `ruff check` (non-blocking, informational),
  - `compileall` syntax check,
  - import smoke test (`from app.main import app`),
  - **`pytest -m "not live and not migrations"`** — the unit + non-live regression
    tier (`tests/conftest.py` supplies CI-mirror env; no real services needed),
  - **`pytest -m migrations`** — fresh-DB bootstrap, idempotence, legacy
    `schema.sql` seed and stamped-at-head no-op against throwaway DBs on the pg16
    service (task 016 / ADR-011). This makes "ORM column with no migration" a CI
    failure.
  - **`schema.sql` loaded into a fresh pgvector Postgres** (validates the full DDL).
- **ci-success** — aggregate status; set this as the single required check in
  branch protection.

## What CI deliberately does *not* run

The **live tier** (`tests/live/`, plus live-marked regressions, plus the 13
standalone `apps/api/test_*.py` scripts it wraps) needs a running API on
`localhost:8000`, Ollama, and real provider keys — so it stays local-only, run with
`pytest -m live` after `./start.sh`. CI covers everything that does not need live
models: lint, types, imports, builds, the unit and migration tiers, and the DB
schema. Full contract: [`standards/testing.md`](../../standards/testing.md).

## Deploy (CD)

`deploy.yml` ships the **backend** to the EC2 host (`ap-south-1`) after CI succeeds
on `main` (or via `workflow_dispatch`). Transport is **AWS SSM RunCommand
authorized by GitHub OIDC** — CD holds no SSH keys and no long-lived AWS
credentials; the assumed role's trust policy is scoped to this repo's `main` ref
(the `sub` claim uses the immutable-ID form, so the trust condition must match
that). The on-server steps — dependency install, `alembic upgrade`, systemd
restart, health check and rollback — live in
[`../../scripts/deploy-server.sh`](../../scripts/deploy-server.sh). Rollback
restores code but **not** schema, so migrations must stay backward-compatible.

The **frontend** is not in this workflow: the Vercel project is git-integrated and
auto-deploys merges to `main`. Never run `vercel deploy --prod` by hand — a
stale-checkout manual deploy reverted production on 2026-07-21. If a manual deploy
is truly unavoidable, use the guarded
[`../../scripts/deploy-web.sh`](../../scripts/deploy-web.sh).

## Required secrets

Settings → Secrets and variables → Actions. CodeQL and dependency-review need
nothing beyond the built-in `GITHUB_TOKEN`.

| Secret | Required | Purpose |
|--------|----------|---------|
| `AWS_DEPLOY_ROLE_ARN` | yes | IAM role assumed via OIDC (SendCommand on the instance). |
| `EC2_INSTANCE_ID` | yes | Target instance (`i-…`). |
| `GROQ_API_KEY` | optional | Synced to the server as `OPENAI_API_KEY` (Groq is the OpenAI-compatible provider). |
| `GEMINI_API_KEY` | optional | Gemini provider. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | optional | Google Calendar OAuth client (the redirect URI must also be whitelisted in Google Console). |
| `OAUTH_STATE_SECRET` | optional | Signs OAuth state. |
| `BACKUP_S3_BUCKET` | optional | Nightly Postgres dump target ([`backup-db.sh`](../../scripts/backup-db.sh)); the cron no-ops until it's set. |

The optional secrets are synced into the server's `apps/api/.env` on **every**
deploy (`sync_env` in `deploy-server.sh`) — to rotate a key, update it here and
re-run this workflow. Keys never belong in committed source; a set was leaked
through `config.py` history once and had to be revoked.
