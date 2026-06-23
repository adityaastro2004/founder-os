# Architecture — Founder OS

> Read this before any structural change (new module, schema change, new router,
> cross-agent change). Paths are relative to the git root unless noted.

## Monorepo layout

Turborepo + npm workspaces, nested under `founder-os/founder-os/`:

- `apps/api` — Python 3.14 / FastAPI backend (standalone; not in the npm graph).
- `apps/web` — Next.js 16 dashboard. Imports `packages/ui`.
- `apps/docs` — Next.js docs site (WIP).
- `packages/ui` — shared React components.
- `packages/eslint-config`, `packages/typescript-config` — shared config.

Build graph: `web`/`docs` depend on the shared packages; `api` is independent.

## Backend request & auth flow

1. Browser (Clerk session) → Next.js → FastAPI with `Authorization: Bearer <JWT>`.
2. `app/auth.py` verifies the Clerk JWT against cached JWKS (RS256, 1h cache) and
   yields a `ClerkUser` via the `require_auth` dependency (`optional_auth` for
   public-ish routes).
3. Routers are registered in `app/main.py` (`include_router` for each
   `app/api/*_routes.py`). Dev-only `test_router` mounts when `APP_ENV=development`.
4. Lifespan (`app/main.py`) runs `init_db → init_redis → start_scheduler` on
   startup and the reverse on shutdown.

## Agent system (product runtime) — `app/agents/`

The heart of the product. Key components:

- **`base.py` — `BaseAgent`**: common interface; wires memory, tools, execution,
  and delegation for every specialist.
- **`execution.py` — `ExecutionEngine`**: step-based LLM loop with parallel tool
  execution (LLM → tools → loop until done).
- **`orchestrator.py` — Orchestrator**: Stripe-Minions pattern
  (Analyse → Plan → Delegate → Synthesise); agents-as-tools, the LLM picks the workflow.
- **`agents.py`** — the specialists: Planner, Content, Research, Ops, Product, Support.
- **`registry.py`** — agent factory + wiring (builds the registry, injects deps).
- **`router.py` — `AgentRouter`**: Agent-to-Agent (A2A) capability-based routing.
- **`tools.py` / `builtin_tools.py` / `tool_protocol.py`** — `ToolRegistry`
  (MCP-compatible registration + closure injection) and the 12 built-in tools.
- **`mcp_adapter.py` / `mcp_tools.py`** — MCP (stdio + SSE) external tool servers.
- **`approval.py` — `ApprovalGate`**: 3-tier risk classification (LOW/MEDIUM/HIGH);
  HIGH/irreversible actions require human approval.
- **`event_bus.py` — `EventBus`**: Redis Pub/Sub for inter-agent events.
- **`memory.py` — `AgentMemory`**: 4 layers — Conversation, Working (Redis),
  Shared (Redis), Long-term (pgvector).
- **`llm.py`** — provider abstraction with 3-tier fallback (Ollama → Anthropic →
  Gemini / OpenAI-compatible). No call site assumes a specific vendor.

### Built-in tools (12)

`delegate_task`, `search_knowledge`, `web_search`*, `get_business_metrics`*,
`create_task`, `list_tasks`, `update_task_status`, `save_draft`,
`get_integrations`, `get_writing_style`, `get_current_datetime`,
`store_working_memory`. (* = stub/placeholder — see [requirements.md](requirements.md).)

## Company State Engine — `app/state/` (the moat; see ADR-009)

The canonical, living model of the company and the product's central differentiator. A
**structured, non-decaying "current truth"** — typed entities (`goal`, `project`, `task`,
`decision`, `metric`, `person`, `meeting`, `note`) + typed relations + provenance — distinct
from the *recall* layers below. Founder pain it owns: fragmentation across Slack/GitHub/
Stripe/Obsidian/Notion, where no system knows the *company*. Each external tool becomes a
synchronization endpoint reconciled into and out of this model.

Wrapped in the **five loops**: Observe → Remember → Understand → Execute → Learn.

- **Observation layer (`app/state/sources/`)** — passive adapters that watch the founder's
  tools and emit raw events. **Obsidian first** (local vault file sync, slice 1);
  GitHub/Stripe/Slack/Calendar/Notion later. This is the **Observe** loop.
- **Reconciler (`app/state/reconciler.py`)** — the Observe→Remember core, reused by every
  feed: record observation (idempotent) → write-gate → dedup-on-ingest → create/merge entity
  with provenance → maintain relations → mirror into RAG/memory.
- **Three feeds, each provenance-tagged:** `observed` (tool adapters), `user_doc` (founder-
  provided docs — extends the knowledge ingestion path), `system` (agent-written memories +
  Hermes procedural skills). Trust: `user_doc` > `observed` > `system`.
- **Hygiene system (anti-bloat):** (1) write-gate — store only if novel/specific/durable;
  (2) provenance trust-weighting; (3) dedup-on-ingest (semantic match → merge, not insert);
  (4) decay + composite scoring (reuses `memory_pages` machinery); (5) periodic **Curator**
  pass (merge/archive/surface). Slice 1 ships (1)+(3); the rest is designed-for.

### Tables (Alembic only)

`state_sources` (registered source + sync cursor), `state_observations` (raw inbound events;
idempotency + audit), `company_state_entities` (typed canonical entities + provenance/
confidence/pin), `state_relations` (typed edges, `memory_links`-style).

### Relationship to the existing memory layers (no duplication)

The State Engine is a **fourth, distinct** layer. `knowledge_items` (RAG) = unstructured doc
recall; `memory_pages`/`memory_links` (temporal KG) = episodic/semantic memory that decays;
4-layer agent memory = in-flight per-run context; **State Engine = authoritative normalized
state that does not decay.** Memory/RAG remain the recall substrate; ingestion feeds *both*.

Full design: [docs/superpowers/specs/2026-06-22-company-state-engine-design.md](superpowers/specs/2026-06-22-company-state-engine-design.md).

## RAG / retrieval — `app/retrieval/`

Chunker → embedder → retriever over `knowledge_items` (pgvector). Embeddings via
Ollama `nomic-embed-text` (1536 dims) or OpenAI `text-embedding-3-small`. Hybrid
search exposed through `knowledge_routes.py`.

## Memory & temporal knowledge graph

- 4-layer agent memory (above) for in-flight context.
- Temporal knowledge graph in `memory_pages` + `memory_links`
  (`planner_models_db.py`): composite scoring, spaced-repetition review, entity
  linking, typed relationships. Exposed via `memory_routes.py`.

## Background work & scheduling

- **Celery** (`celery_app.py`) — Redis broker, queues `default`, `agents`,
  `orchestrator`; long orchestrations run async with status polling
  (`queue_routes.py`).
- **APScheduler** (`scheduler.py`) — cron jobs, e.g. weekly plan generation
  Monday 08:00 IST.

## Data model — `app/models.py`, `planner_models_db.py`, `schema.sql`

~28 tables. Load-bearing ones:

- `users` (Clerk auth + subscription), `founder_profiles` (business context).
- `agents` (registry: name, system_prompt, model, capabilities),
  `user_agent_configs` (per-user overrides).
- `tasks`, `task_feedback` (learning loop), `workflow_templates`.
- `knowledge_items` (pgvector), `activity_log` (event history).
- `approvals` (queue), `approval_preferences` (per-tool: always_allow / ask / always_deny).
- Planner/memory: `business_profiles`, `weekly_plans`, `memory_pages`, `memory_links`.

Schema changes go through **Alembic** (`apps/api/alembic/`), not hand-edited SQL.

## Frontend — `apps/web`

App Router with route groups: `(auth)`, `(dashboard)`, `(onboarding)`. Dashboard
pages: overview, chat (SSE streaming), agents (live status), planner, tasks,
knowledge, memory, content-ideas, settings. Shared client utilities in `lib/`:
`useApi` (stable, ref-based token), `useEventSource` (SSE with backoff),
`useStreamingFetch` (POST-based SSE for chat). See [standards/coding.md](../standards/coding.md).

## Infrastructure

Docker Compose: `pgvector/pgvector:pg16` + `redis:7-alpine`. CORS middleware on
the API for the Clerk frontend. Config via `pydantic-settings` (`config.py`) from
`apps/api/.env` and `apps/web/.env.local`.
