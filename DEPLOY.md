# Deploying Founder OS (cheaply)

Two halves:

- **Frontend** (Next.js) → **Vercel** free Hobby tier ($0).
- **Backend** (API + Celery worker + Postgres/pgvector + Redis + optional n8n) →
  **one small Linux host**.

> **Live production topology (what actually runs today):** the backend is on a
> single **EC2 host in `ap-south-1`**, where `founder-api` and `founder-celery` run
> as **systemd units** (venv at `apps/api/.venv`), Postgres + Redis run as
> localhost-only Docker containers, and a cron job dumps Postgres to S3 nightly.
> CD is fully automated over **AWS SSM RunCommand + GitHub OIDC** — see **Part 4**
> below. Parts 1–3 below are the
> self-host-it-yourself recipe (Docker Compose + Caddy) — a valid alternative that
> the `docker-compose.prod.yml`/`Caddyfile` in the repo still support, but *not*
> the mechanism the hosted instance uses.

> All Docker Compose commands below run from the monorepo dir:
> `founder-os/founder-os/` (the repo is double-nested; the compose file lives there).

The single biggest cost lever: **do not self-host Ollama.** An 8B model needs
~8–16 GB RAM. Use a hosted LLM with a free tier (Groq / Gemini) so the box stays tiny.

---

## Part 1 — Backend on a VPS (recommended, ~$5/mo)

A **Hetzner CX22** (2 vCPU / 4 GB, ~€4/mo) or any $5 droplet handles the whole stack.

```bash
# 1. On the server: install Docker + compose plugin
curl -fsSL https://get.docker.com | sh

# 2. Clone and enter the monorepo dir
git clone <your-repo> && cd founder-os/founder-os

# 3. Configure
cp .env.production.example .env.production
nano .env.production          # fill DB password, Clerk, LLM key, callback secret,
                              # and API_DOMAIN / N8N_DOMAIN / ACME_EMAIL
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # → WORKFLOW_CALLBACK_SECRET

# 4. Launch (add --profile n8n to include the workflow engine)
docker compose --env-file .env.production --profile n8n -f docker-compose.prod.yml up -d --build

# 5. Verify
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml exec -T api curl -fsS http://localhost:8000/openapi.json > /dev/null && echo "API up"
```

The `api` service runs `alembic upgrade head` on start (creates the schema +
pgvector).

**HTTPS is built in.** A **Caddy** reverse proxy is the only service exposed to the
internet (ports 80/443); the API and n8n stay on the internal network. Caddy fetches
Let's Encrypt certs automatically for the domains you set:
- Point **A records** for `API_DOMAIN` and `N8N_DOMAIN` at the server's public IP.
- Set `API_DOMAIN`, `N8N_DOMAIN`, `ACME_EMAIL` in `.env.production`.
- Set `NEXT_PUBLIC_API_URL` (Vercel) to `https://$API_DOMAIN`, and add that origin to `CORS_ORIGINS`.

> Left at defaults (no domain), Caddy serves on `localhost` with a self-signed cert —
> fine for a smoke test, not for production.

**Keep the API at 1 replica** — APScheduler runs inside the API process, so a
second replica would double-fire the weekly-plan jobs.

---

## Part 2 — Frontend on Vercel (free)

1. New Vercel project from this repo.
2. **Root Directory** → `founder-os/founder-os/apps/web` (Turborepo monorepo).
3. Env vars:
   - `NEXT_PUBLIC_API_URL` = your public API URL (e.g. `https://api.your-domain.com`)
   - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` (production instance)
   - `NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in`, `…SIGN_UP_URL=/sign-up`,
     `…AFTER_SIGN_IN_URL=/dashboard`, `…AFTER_SIGN_UP_URL=/onboarding`
   - `NEXT_PUBLIC_N8N_BASE_URL` (only if running n8n; enables the "Edit in n8n" link)
4. Deploy. Then add the Vercel domain to `CORS_ORIGINS` in `.env.production` and
   restart the API.

---

## Part 3 — AWS EC2 free tier: yes, with caveats

**Short answer:** possible and can be **$0 for 12 months**, but the free instance
is RAM-starved, so you must offload the heavy bits.

The free tier gives a **t3.micro / t2.micro: 1 vCPU, 1 GB RAM**, 750 hrs/mo (one
instance 24/7), 30 GB disk — **for 12 months only**, then ~$7–8/mo.

**1 GB RAM is the constraint.** Postgres + Redis + API + Celery worker + n8n will
OOM on 1 GB. Two ways to make it fit:

**Option A — all-in-one on the micro (tight but free):**
- Add swap so builds/peaks don't kill it:
  ```bash
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  ```
- Use the hosted LLM (no Ollama) and **skip n8n** initially (don't pass `--profile n8n`).
- Run the compose file as in Part 1. Expect it to be slow but functional for demo/light use.

**Option B — micro for compute, free managed data (the clean $0 combo):**
- **Neon** free Postgres (supports `CREATE EXTENSION vector`) → set `DATABASE_URL` /
  `DATABASE_URL_SYNC` to the Neon connection strings (host is external, not `postgres`).
- **Upstash** free Redis → set `REDIS_URL` to the Upstash URL.
- On the EC2 micro, run **only** `api` + `worker` (comment out `postgres`/`redis`
  in the compose, or just point the URLs off-box and don't start those services).
- This frees ~500 MB+ of RAM and is far more stable on 1 GB.

Either way: the **Security Group** should allow inbound **80 + 443** (Caddy) and **22**
(SSH) only — the API (8000) and n8n (5678) are not published to the host, so don't open them.

> If 1 GB proves painful, a **t3.small (2 GB)** is ~$15/mo on-demand — or just use the
> Hetzner box in Part 1, which is cheaper *and* roomier than a paid EC2.

---

## Part 4 — Automated deploys (GitHub Actions) — *the live mechanism*

This is what the hosted EC2 backend actually uses.
[`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) deploys the backend
after the **CI** workflow passes on `main` (or on manual `workflow_dispatch`).

**Transport is AWS SSM RunCommand authorized by GitHub OIDC — there are no SSH keys
and no long-lived AWS credentials in the repo.** The workflow assumes an IAM role via
OIDC (trust policy scoped to this repo's `main` ref), then `aws ssm send-command`
runs [`scripts/deploy-server.sh`](scripts/deploy-server.sh) on the instance. The
on-server steps (as root, checkout already reset to `origin/main`):

1. **`sync_env`** — patch selected secrets into `apps/api/.env` and **pin
   `APP_ENV=production` / `DEBUG=false`** (the load-bearing gate that disables the
   dev-only `x-test-user` auth bypass — a fresh box must never be left at the
   development default).
2. `pip install -r requirements.txt` into the venv.
3. `alembic upgrade head`.
4. `systemctl restart founder-api founder-celery`.
5. Health check → **automatic rollback** to the previous SHA on failure. Rollback
   restores *code but not schema*, so migrations must stay backward-compatible for
   at least one release.

**Repo secrets** (Settings → Secrets and variables → Actions):

| Secret | Required | Purpose |
|---|---|---|
| `AWS_DEPLOY_ROLE_ARN` | yes | IAM role assumed via OIDC (`ssm:SendCommand` on the instance). |
| `EC2_INSTANCE_ID` | yes | Target instance (`i-…`). |
| `GROQ_API_KEY` | optional | Synced to the server as `OPENAI_API_KEY` (Groq is the OpenAI-compatible provider). |
| `GEMINI_API_KEY` | optional | Gemini provider. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | optional | Google Calendar OAuth client. |
| `OAUTH_STATE_SECRET` | optional | Signs OAuth state. |
| `BACKUP_S3_BUCKET` | optional | Nightly Postgres dump target ([`scripts/backup-db.sh`](scripts/backup-db.sh)); the cron no-ops until it's set. |
| `METRICS_TOKEN` | optional | Bearer token guarding `GET /metrics` (ADR-018). Until it's set, the endpoint is **not mounted** in production — fail closed. Generate with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. |

The optional secrets are re-synced into `apps/api/.env` on **every** deploy — to
rotate a key, update it here and re-run the workflow. Never commit keys (a set was
once leaked via `config.py` history and had to be revoked). Trigger a manual deploy
via **Actions → Deploy → Run workflow**.

**Nightly backups:** `deploy-server.sh` installs `/etc/cron.d/founder-os-db-backup`,
which runs [`scripts/backup-db.sh`](scripts/backup-db.sh) to `pg_dump` the database
to S3 (gated on `BACKUP_S3_BUCKET`).

**Metrics / Grafana Cloud (ADR-018):** the API exposes a token-guarded
`GET /metrics`, scraped by a Grafana Alloy container that remote-writes to Grafana
Cloud's free tier. On this systemd topology Alloy runs with `--network host` and
scrapes `localhost:8000`; it is **not** started by `deploy-server.sh`, because a
collector that crash-loops on a missing credential must never be able to fail a
product deploy. The three Grafana Cloud credentials also bypass `sync_env` — their
tokens contain `=`/`+`, which `patch_var`'s charset check refuses by design — and
live in `/etc/founder-os/alloy.env` instead. One-time setup, verification, and the
dashboard/alert import steps are in
[`ops/grafana/README.md`](ops/grafana/README.md). `/metrics` is never exposed by
Caddy.

> **Frontend:** the Vercel project is **git-integrated** and auto-deploys merges to
> `main` on its own — no Action needed. **Never run `vercel deploy --prod` by hand**
> — a stale-checkout manual deploy reverted production on 2026-07-21. If a manual
> deploy is truly unavoidable, use the guarded
> [`scripts/deploy-web.sh`](scripts/deploy-web.sh), which refuses unless `HEAD ==
> origin/main` and the worktree is clean.

---

## Cost cheat-sheet

| Path | Monthly | Notes |
|---|---|---|
| Hetzner CX22 + Vercel + Groq | **~$5** | Roomiest cheap option; recommended |
| EC2 t3.micro (all-in-one) + Vercel + Groq | **$0 (12 mo)** | 1 GB is tight; add swap, skip n8n |
| EC2 micro + Neon + Upstash + Vercel + Groq | **$0 (12 mo)** | Most stable free combo |
| Railway/Render (managed multi-service) | ~$5–20 | Easiest DX, usage-based |

---

## Gotchas (all stack-specific)

- **Migrations**: handled by the `api` service (`alembic upgrade head`). Never hand-edit `schema.sql`.
- **Durable orchestrator (ADR-017)**: `alembic upgrade head` also creates the LangGraph
  `checkpoint*` tables (migration `0003_langgraph_checkpoint`, via `PostgresSaver.setup()`).
  The checkpointer uses **psycopg3**, not the app's asyncpg — it derives a plain
  `postgresql://…` DSN from `DATABASE_URL` (strips `+asyncpg`), so the same Postgres and
  credentials work with no extra config. It opens a pooled `AsyncPostgresSaver` in the API
  lifespan; if that fails the API still boots and orchestration simply degrades to
  non-durable (no crash-resume / no `/orchestrate/resume`). Optional
  `CHECKPOINTER_POOL_MAX` (default 10) sizes the pool. The human-in-the-loop resume path is
  `POST /api/agents/orchestrate/resume` (`{session_id, answer}`).
- **`WORKFLOW_CALLBACK_SECRET` is mandatory** when `APP_ENV != development` — the app
  refuses to boot without ≥43 chars. Generate with `token_urlsafe(32)`.
- **CORS_ORIGINS** is a JSON array env var — include your exact web origin(s).
- **APScheduler in-process** → API stays at 1 replica.
- **Embeddings need a provider with an embeddings endpoint** (Groq has none). Use OpenAI
  `text-embedding-3-small` (cheap, 1536 dims) or a small Ollama just for embeddings.
- **n8n**: set `N8N_API_KEY` (generated in the n8n UI) or the API's n8n client gets 401;
  set public `WEBHOOK_URL`/`N8N_HOST` so callbacks resolve.
- **Clerk**: use production-instance keys for both web and API; the API only needs
  `CLERK_ISSUER` + `CLERK_JWKS_URL`.
