# Requirements & Constraints — Founder OS

> What the system must do, the constraints it operates under, and — importantly —
> what is **real vs scaffolded** today so agents don't mistake a stub for a feature.

## Functional requirements

- **Single entry point**: users interact with the Orchestrator; it decomposes,
  delegates (A2A), and synthesises. Users never pick an agent.
- **Specialist coverage**: Planner, Content, Research, Ops, Product, Support.
- **Grounded answers**: agents retrieve from the pgvector knowledge base before
  acting where relevant.
- **Persistent memory**: 4-layer agent memory + temporal knowledge graph survive
  across sessions.
- **Weekly planning**: ICE-scored priorities, Google Calendar sync, auto-generated
  Monday mornings.
- **Background execution**: long orchestrations run via Celery with status polling
  and cancellation.
- **Multi-provider LLM**: pluggable provider with graceful fallback; Ollama default.

## Constraints (non-negotiable)

- **Human-in-the-loop approval** — 3-tier risk classification:
  - **LOW** — auto-run (read-only, internal).
  - **MEDIUM** — run per user preference (`approval_preferences`: always_allow / ask / always_deny).
  - **HIGH** — irreversible / external side effects → **must** be gated on human approval.
  Never downgrade a risk tier or bypass the gate to make a flow complete.
- **Auth** — every non-public route requires a valid Clerk JWT (`require_auth`).
- **Secrets** — never commit `.env`; never log tokens, API keys, or full JWTs.
- **Provider neutrality** — no code path may hard-require a specific LLM vendor.
- **OSS / local-first defaults** — the system must run with Ollama + Postgres +
  Redis, no paid API required.
- **Schema migrations** — via Alembic only.

## Known gaps / placeholders (real vs scaffolded)

Treat these as **not production-ready**. Don't build on them assuming they work;
if a task touches them, flag the gap.

- `web_search` tool — **stub** (placeholder for Tavily/SerpAPI; no live search).
- `get_business_metrics` tool — **stub** returning mock data (`app/agents/mock_data.py`).
- **No test framework configured** — backend tests are standalone `test_*.py`
  scripts; frontend has no tests. See [standards/testing.md](../standards/testing.md).
- **No backend linter/formatter** configured (no black/ruff/flake8 in requirements).
- `apps/docs` — Next.js docs site is minimal / WIP.
- Dev-only `test_routes.py` runs **without auth** when `APP_ENV=development` — never
  enable it in production.

## Definition of done (for changes in this repo)

1. Behavior matches the request and the rules in [CLAUDE.md](../CLAUDE.md).
2. A test or a manual verification exists and **passes** (output shown).
3. Standards followed ([coding](../standards/coding.md), [api](../standards/api.md),
   [testing](../standards/testing.md)).
4. Security model intact (auth + approval gate + secrets).
5. Schema changes have an Alembic migration.
6. Reviewer findings addressed or explicitly deferred with a reason.
