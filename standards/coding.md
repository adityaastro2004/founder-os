# Coding Standards — Founder OS

> Match the surrounding code's idiom, comment density, and naming. These are the
> conventions already in the codebase — follow them rather than introducing new ones.

## Python (backend, `apps/api`)

- **Async-first.** Routes, DB access, Redis, and LLM calls are `async`. Use the
  async SQLAlchemy session and `asyncpg`; never block the event loop with sync IO.
- **Type hints everywhere.** Use modern syntax (`str | None`, `list[str]`,
  `from __future__ import annotations`). Dataclasses for simple value objects
  (see `ClerkUser` in `app/auth.py`).
- **Config via `pydantic-settings`.** All config flows through `app/config.py`
  (`get_settings()`), read from `.env`. Never read `os.environ` ad hoc; never
  hardcode secrets, URLs, or model names.
- **Module layout** under `app/`: routers in `app/api/*_routes.py`, product agents
  in `app/agents/`, ORM in `models.py` / `planner_models_db.py`, infra singletons
  in `database.py` / `redis.py` / `celery_app.py` / `scheduler.py`.
- **SQLAlchemy 2.0 patterns.** Declarative models on `Base`; import models in
  `main.py` so they register with `Base.metadata`. Schema changes → Alembic
  migration, never hand-edit `schema.sql`.
- **Logging, not prints**, in product code (`logging.getLogger(__name__)`; root
  config is set in `main.py`). `test_*.py` scripts may print results.
- **Errors**: raise `HTTPException` with the right status in routes; let domain
  errors surface with context — don't swallow exceptions silently.
- **Comments** are sparse and explain *why*, using the existing `# ──` section
  divider style where a file already uses it. Don't over-comment obvious code.

## TypeScript / React (frontend, `apps/web`)

- **App Router + server components** by default; add `"use client"` only when you
  need interactivity/hooks. Route groups: `(auth)`, `(dashboard)`, `(onboarding)`.
- **API access through the `lib/` hooks** — reuse, don't reinvent:
  - `useApi` (`lib/use-api.ts`) — stable, ref-based token client; prevents re-renders.
  - `useEventSource` (`lib/use-event-source.ts`) — SSE with Clerk auth + exponential backoff.
  - `useStreamingFetch` (`lib/use-streaming-fetch.ts`) — POST-based SSE for chat.
  - `lib/api.ts` — base client/config.
- **Strict TypeScript** (`tsc --noEmit` must pass). No implicit `any`; respect
  strict null checks.
- **Styling**: Tailwind CSS 4 design tokens + `clsx`; icons from `lucide-react`.
  Shared components live in `packages/ui` or `(dashboard)/_components/`.
- **Auth**: Clerk (`@clerk/nextjs`). Don't roll your own session handling.

## Cross-cutting

- **Reuse before adding.** Search for an existing util/hook/tool/model before
  writing a new one (the agent `ToolRegistry`, the `lib/` hooks, ORM models).
- **No new dependency** without a reason; prefer what's already in
  `requirements.txt` / `package.json`.
- **Keep diffs minimal and on-topic.** Don't reformat unrelated code.
- **Provider neutrality**: backend code goes through `app/agents/llm.py`, never a
  vendor SDK directly in business logic.
