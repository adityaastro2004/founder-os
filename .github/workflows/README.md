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
  - **`schema.sql` loaded into a fresh pgvector Postgres** (validates the full DDL).
- **ci-success** — aggregate status; set this as the single required check in
  branch protection.

## What CI deliberately does *not* run

The `test_*.py` suites in `apps/api` are **live-server integration scripts** (httpx
→ `localhost:8000`) that need a running API, Ollama, and an LLM provider. They are
not run in CI because they require live models/secrets. CI validates the static
surface instead: lint, types, imports, builds, and the DB schema. See
[`standards/testing.md`](../../standards/testing.md).

## Deploy (CD)

No deploy steps yet — by design. When a host is chosen (e.g. Vercel for web,
Fly.io/Render for the API, or publishing Docker images to GHCR), add a `deploy.yml`
gated on `ci-success` and `github.ref == 'refs/heads/main'`.

## Required secrets

None today. CodeQL and dependency-review use the built-in `GITHUB_TOKEN`. Add
provider secrets only when CD is wired up.
