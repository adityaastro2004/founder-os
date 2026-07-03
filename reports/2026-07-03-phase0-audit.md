# Phase 0 Audit — 2026-07-03

> Verdicts: PASS / FAIL / BLOCKED. Every verdict has captured output.
> Probe environment: local macOS (Darwin 25.5.0), Docker, Ollama `llama3.1:8b` +
> `nomic-embed-text`, `APP_ENV=development`, branch `phase0-foundation-revamp`.
> Spec: docs/superpowers/specs/2026-07-03-phase0-foundation-revamp-design.md

| # | Subsystem | Verdict | Evidence section |
|---|-----------|---------|------------------|
| 1 | Boot (Docker, Alembic, uvicorn, Celery, web) | **PASS** | §1 |
| 2 | Auth path (Clerk + dev bypass + test_routes gating) | **PASS** | §2 |
| 3 | Orchestrator + agent chat | | §3 |
| 4 | Memory (4-layer + temporal KG) | | §4 |
| 5 | Knowledge / RAG | | §5 |
| 6 | Planner + weekly plan + APScheduler | | §6 |
| 7 | Google Calendar | | §7 |
| 8 | Workflows / automations (AOV + n8n) | | §8 |
| 9 | Approval gate | | §9 |
| 10 | Remaining routers (crawler, billing, settings, activity, history, queue) | | §10 |
| 11 | Frontend | | §11 |

## §1 Boot

**Verdict: PASS.** `./start.sh` booted cleanly end-to-end (2026-07-03 ~14:29 local).

- start.sh: `✔ Ollama found` · `✔ nomic-embed-text model available` · `✔ Migrations applied` · `✔ API server running (PID 1757)` · `✔ Celery worker running (PID 1787)` · `✔ Web dev server running (PID 1877)`; n8n profile active.
- Health: `GET /api/health` → `{"healthy": true, "checks": {"api": "ok", "postgres": "ok", "redis": "ok"}}`
- Web: `GET http://localhost:3000` → `200`
- Containers: `postgres Up (healthy)`, `redis Up (healthy)`, `n8n Up (healthy)`
- Alembic: `alembic current` → `0001_workflow_engine (head)`
- Celery: `celery@Adityas-MacBook-Air-5.local ready.` (queues default,agents,orchestrator)

*Note (doc nit, not a failure):* the health endpoint is `/api/health`; the `/api` prefix
lives on the router in `app/api/routes.py:9`, not in `main.py`.

## §2 Auth path

**Verdict: PASS.** The dev bypass and dev test routes are both provably hard-gated.

- `app/auth.py:137-151` `_dev_test_user`: returns `None` when `settings.APP_ENV != "development"` **before** the `x-test-user` header is ever read.
- `app/main.py:105-107`: `test_router` mounted only inside `if settings.APP_ENV == "development":` (comment: "Dev-only test routes (no auth required)").
- Live behavior (dev): `GET /api/agents` without header → **401**; with `x-test-user: audit-user` → **200** (agents list returned).
- Deployment requirement carried to Phase 5: production must set `APP_ENV` ≠ `development`; both the bypass and `test_routes` then vanish.

*Observation for §3:* the agent registry lists `"model": "claude-sonnet-4-20250514"` on
agent definitions while `LLM_PROVIDER=ollama` — display/DB field vs. runtime provider;
checked under §3.

## §3 Orchestrator + agent chat

(filled by audit)

## §4 Memory

(filled by audit)

## §5 Knowledge / RAG

(filled by audit)

## §6 Planner + weekly plan + APScheduler

(filled by audit)

## §7 Google Calendar

(filled by audit)

## §8 Workflows / automations

(filled by audit)

## §9 Approval gate

(filled by audit)

## §10 Remaining routers

(filled by audit)

## §11 Frontend

(filled by audit)

## Ranked fix list

(filled at end of Stage 1)
