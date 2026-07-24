# Founder OS — Monorepo

This is the Turborepo monorepo for **Founder OS**, an autonomous AI operating system
for solo founders and tiny teams. See the [project README](../readme.md) for the full
vision and pitch, and [`docs/architecture.md`](../docs/architecture.md) for the
detailed architecture.

**The moat is the Company State Engine** (`apps/api/app/state/`) — a canonical, living
model of the company (goals · projects · tasks · decisions · metrics · people ·
meetings) fed by passive multi-channel observation and mirrored back into the tools
the founder already uses via pluggable adapters in `apps/api/app/integrations/`
(Obsidian shipped, Notion + Google Calendar in flight). Workflow auto-generation
(n8n-backed) still exists but has been demoted from the pitch.

## Apps

| App | Stack | Description |
|-----|-------|-------------|
| `apps/api` | FastAPI + Python 3.14 | Multi-agent AI backend — ~20 routers, Company State Engine, 43 DB tables / 6 views, Celery queue, APScheduler, integration adapters |
| `apps/web` | Next.js 16 + React 19 + Tailwind v4 | Dashboard frontend (App Router) — Clerk auth, SSE streaming, background chat, dark mode, Stripe billing |
| `apps/docs` | Next.js | Documentation site (WIP) |

## Packages

| Package | Description |
|---------|-------------|
| `packages/ui` | Shared React component library |
| `packages/eslint-config` | Shared ESLint configuration |
| `packages/typescript-config` | Shared TypeScript configuration |

## Frontend (`apps/web`)

### Tech Stack
- **Next.js 16** with App Router (server components) + **React 19**
- **Tailwind CSS v4** with CSS design tokens (see `apps/web/brand.md`)
- **Clerk** (`@clerk/nextjs`) for authentication — theme-aware in dark mode
- **react-markdown + remark-gfm** — agent chat rendered as markdown
- **posthog-js** — product analytics
- **SSE (Server-Sent Events)** for the real-time agent activity feed
- **Streaming fetch** for chat responses

### Dashboard Pages

`app/(dashboard)/dashboard/…` — Dashboard, Chat, Agents, Planner, Tasks, Knowledge,
Memory, Apps (integrations / state sources), Automations, Workflows, Content Ideas,
Billing, Settings. Plus `(auth)` (sign-in / sign-up) and `(onboarding)` route groups.

### Key Frontend Features
- **Background chat** (`lib/chat-store.tsx`) — a `ChatProvider` in the dashboard
  layout owns chat state so orchestration runs keep streaming across tab navigation
  (its own detached DB session; never aborted on unmount).
- **Dark mode** — an owned `ThemeProvider` + toggle re-values the `.dark` design
  tokens; Clerk components are themed to match (not just `prefers-color-scheme`).
- **Markdown agent chat** — responses render through a shared kit `Markdown` component.
- **Stable API hook** (`use-api`) — `useCallback`-wrapped with ref-based token access,
  prevents re-render loops.
- **SSE hook** (`use-event-source`) — Clerk auth, exponential backoff reconnect,
  ref-stabilized token.
- **Streaming fetch** (`use-streaming-fetch`) — POST-based SSE for chat.
- **4-step onboarding wizard** — business info, goals, metrics, preferences (bounded
  numerics validated front and back).
- **Responsive design** — mobile-first grids, `100dvh` viewport, adaptive layouts.

## Backend (`apps/api`)

### Tech Stack
- **FastAPI** with async endpoints (~20 `*_routes.py` routers)
- **PostgreSQL 16 + pgvector** — 43 tables, 6 views (full DDL in `apps/api/schema.sql`;
  schema changes go through **Alembic**, never a hand-edited `schema.sql`)
- **Redis 7** — pub/sub for the EventBus, agent state caching, 4-layer memory
- **Celery 5** — background task queue (`default,agents,orchestrator` queues)
- **APScheduler** — weekly plan auto-generation (Mon 08:00 IST)
- **Clerk** — JWT auth validation via the `require_auth` dependency
- **Stripe** billing · **PostHog** analytics
- Security middleware — headers, rate limiting, log redaction, SSRF guard

### Company State Engine (`app/state/`)
The flagship. `service · mirror · reconciler · renderer · write_gate · dedup · models`
reconcile three feeds — `observed` (from tools), `user_doc` (docs you hand it), and
`system` (agent memories + skills) — into one canonical company model, kept clean by a
hygiene system (write-gate, dedup, decay). Mirrored outward through state-source
adapters in `app/integrations/`: **obsidian**, **notion**, **google_calendar**.

### Agent System
- **Product runtime agents**: **Orchestrator** + specialists (**Planner, Content,
  Research, Support**). The Orchestrator is Stripe-Minions-inspired: Analyse → Plan →
  Delegate → Synthesise, agents-as-tools.
- **3-tier LLM fallback** (pluggable): Ollama (default) → Anthropic / Gemini /
  OpenAI-compatible (Groq).
- **Approval Gate** — 3-tier risk classification (LOW / MEDIUM / HIGH).
- **A2A protocol** — agent-to-agent delegation without user routing.
- **Token-optimized** — per-request LLM usage was cut across the stack (tool-result
  clipping, capped memory-block rendering, dropped redundant tool rounds, Anthropic
  prompt caching). See [`reports/2026-07-21-token-optimization.md`](../reports/2026-07-21-token-optimization.md).

### Real-time System
- **EventBus** — Redis pub/sub for SSE event streaming
- **SSE endpoints**: `/api/activity/stream`, `/api/agents/orchestrate/stream`
- **Tool event emission** — every tool call/result emitted to the event bus

## Quick Start

The **preferred** path is the one-command launcher (Docker → Ollama → migrations →
API + Celery + web):

```bash
./start.sh          # from this dir (founder-os/founder-os/)
./start.sh --stop   # tear everything down
```

First-time setup (the launcher errors if the venv is missing):

```bash
# 1. Frontend deps (npm workspaces — not pnpm)
npm ci

# 2. Backend venv
cd apps/api && python3 -m venv .venv && source .venv/bin/activate \
  && pip install -r requirements.txt
cp .env.example .env   # then fill in Clerk + LLM/provider keys
```

Run the services manually instead of `start.sh`:

```bash
docker compose up -d                                   # PostgreSQL + Redis
cd apps/api && source .venv/bin/activate && alembic upgrade head
uvicorn app.main:app --reload --port 8000
celery -A app.celery_app worker --loglevel=info -Q default,agents,orchestrator
cd ../.. && turbo dev --filter=web                     # Next.js on :3000
```

### Environment Variables

**Frontend** (`apps/web/.env.local`): `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`,
`CLERK_SECRET_KEY`, `NEXT_PUBLIC_API_URL`.

**Backend** (`apps/api/.env` — see `apps/api/.env.example` for the full list):
`DATABASE_URL`, `REDIS_URL`, `CLERK_ISSUER` / `CLERK_JWKS_URL`, `GEMINI_API_KEY`,
`OPENAI_API_KEY` (Groq), Google Calendar OAuth vars, `APP_ENV` (must be `production`
off-dev — it gates the dev-only `x-test-user` auth bypass).

## Development Commands

```bash
turbo dev --filter=web        # frontend, hot reload
turbo build                   # build all apps
turbo lint                    # ESLint (web: --max-warnings 0)
turbo check-types             # next typegen && tsc --noEmit

# Backend tests — pytest, four tiers (contract: standards/testing.md)
cd apps/api && source .venv/bin/activate
pytest                        # unit + non-live regression — needs no services (default)
pytest -m migrations          # needs a pgvector Postgres only
pytest -m live                # needs the full stack on :8000 + Ollama
```

## CI/CD & Deploy

- **CI** (`.github/workflows/ci.yml`) — frontend lint/types/build + backend
  ruff/imports/`pytest` unit + migrations + schema load, aggregated into the required
  `ci-success` check. Run `turbo lint`, `turbo check-types`, `turbo build`, `pytest`
  locally before pushing.
- **Backend deploy** — automated to an EC2 host via **AWS SSM RunCommand over GitHub
  OIDC** (systemd `founder-api` / `founder-celery`). **Frontend** — Vercel git
  integration auto-deploys merges to `main`; never `vercel deploy --prod` by hand.
  Full runbook: [`DEPLOY.md`](../DEPLOY.md) · [`.github/workflows/README.md`](../.github/workflows/README.md).
