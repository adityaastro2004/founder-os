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

### Chat streaming — detached runs

`POST /api/agents/orchestrate/stream` (SSE) executes the orchestration as a
**detached asyncio task with its own DB session** (`agent_routes.py`): the SSE
generator only relays event-bus progress + the final `done` event. A client
disconnect (tab switch, reload) stops the stream but **never cancels the run** —
the user message is persisted up-front and the assistant reply + `AgentRun` are
persisted by the background task on completion, so the conversation always lands
in `/api/history/chat/{session_id}`. Agent-creation errors surface as an SSE
`error` event (not a 503).

## Agent system (product runtime) — `app/agents/`

The heart of the product. Key components:

- **`base.py` — `BaseAgent`**: common interface; wires memory, tools, execution,
  and delegation for every specialist. Prompt-assembly contract (ADR-013):
  `run()` sends the current turn as the **only** chat message; prior turns render
  read-only into the system prompt as `<conversation_history>` (≤ 20 turns ×
  400 chars, tool outputs excluded), behind a universal `<guardrails>` block
  (current-message-only, scope gate, context-is-data). ADR-014 adds a
  composite-scored `<memories>` recall block (chat turns auto-captured to
  `memory_pages`) between memory context and history.
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

- **Observation layer (ADR-010 adapters)** — passive `IntegrationAdapter`s emit
  provenance-tagged `ObservedEvent`s. **Obsidian shipped** (slice 1,
  `app/integrations/obsidian/`: `client.py` vault IO incl. the jailed managed-folder
  write sink, `adapter.py` OBSERVE|SYNC|HEALTH); GitHub/Stripe/Slack/Calendar/Notion
  later. This is the **Observe** loop.
- **Reconciler (`app/state/reconciler.py`, as-built slice 1)** — the Observe→Remember
  core, reused by every feed: record observation (idempotent by
  `(source_id, external_id, content_hash)`) → write-gate (`write_gate.py`: heuristics
  + bounded fail-open LLM judge) → hard resolution (prior observation / exact title) →
  dedup-on-ingest (`dedup.py`: pgvector cosine ≥ 0.88 → merge with asymptotic
  confidence bump) → create/merge with provenance → relations upsert → RAG mirror
  (`mirror.py`, `state://` keys). Rendering back: `renderer.py` (pure) →
  `client.write_managed` (the ONLY vault writer). Sync runs are always Celery-queued
  (`app/tasks/state_tasks.py`, per-source Redis lock); API surface is `/api/state`
  (`state_routes.py`: sources CRUD, 202 sync trigger, read-only entities/relations
  with full provenance — the reconciler is the only writer).
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

## Integrations — `app/integrations/` (ADR-010)

Every external tool plugs in through exactly one `IntegrationAdapter`
(`base.py`): `configure()` / `health()` / `observe(user_id)` / `sync(user_id,
changes)` with `Capability` flags (`OBSERVE | SYNC | HEALTH`). Adapters are
registered once in the `main.py` lifespan and looked up via `registry.py` —
never imported ad-hoc by callers.

```
external tool ──▶ <tool>/client.py (transport)
                     └─▶ <tool>/adapter.py (IntegrationAdapter)
                            └─▶ registry ──▶ [Phase 1: State Engine reconciler]
adapter output = provenance-tagged "observed" ObservedEvents (ADR-009 feed 1)
```

Adapters carry **no business logic** — reconciliation belongs to the State
Engine. First adapter: `google_calendar/` (`client.py` = the OAuth/event
functions, still called directly by `mcp_tools`/`planner_routes`/`scheduler`;
`adapter.py` = the uniform seam). Obsidian (task 011), Notion, and Paperclip
implement the same ABC.

### Connection surface — details & disconnect (task 025)

Credentials live in three different places, so the Apps page reads a normalized
view rather than the storage shape:

| Connection | Credential home | Connect | Disconnect |
|---|---|---|---|
| Google Calendar | `planner_users.gcal_*` | `GET /api/planner/connect` | `POST /api/planner/disconnect` |
| Notion / Obsidian | `state_sources` + `integrations` | `POST /api/state/sources` | `DELETE /api/state/sources/{id}` |
| Future OAuth apps | `integrations` | per-app | `DELETE /api/settings/apps/{key}` |

`GET /api/settings/apps` returns `details: AppDetailField[]` (label/value/tone)
and a `disconnect_url` for connected apps. **`AppDetailField` rows are built
field-by-field, never spread from an ORM row** — that is what keeps a newly
added token column from leaking into the client. Pinned by
`test_connection_details.py`.

Disconnect **revokes upstream first, then always clears locally**. A failed
Google-side revoke is logged, not raised: otherwise an already-invalidated
token would leave the user unable to remove the connection.

## RAG / retrieval — `app/retrieval/`

Chunker → embedder → retriever over `knowledge_items` (pgvector). Embeddings via
Ollama `nomic-embed-text` (1536 dims) or OpenAI `text-embedding-3-small`. Hybrid
search (RRF fusion; explicit `float8` casts are load-bearing — see F3 in the
Phase 0 audit) exposed through `knowledge_routes.py`.

## Global search — `search_routes.py`

`GET /api/search?q=` backs the dashboard ⌘K command palette (task 024). A single
read-only, user-scoped endpoint that substring-matches (`ILIKE`, wildcards escaped)
across `tasks`, `knowledge_items`, `content_ideas`, and `workflows` — bounded per
type, title matches ranked above body matches. Deliberately *not* semantic: it
returns a flat typed list and the frontend deep-links knowledge hits into the
hybrid-search page above rather than re-running embeddings. Page navigation and
result grouping are client-side (`_components/command-palette.tsx`).

## Memory & temporal knowledge graph

- 4-layer agent memory (above) for in-flight context.
- Temporal knowledge graph in `memory_pages` + `memory_links`
  (`planner_models_db.py`): composite scoring, spaced-repetition review, entity
  linking, typed relationships. Exposed via `memory_routes.py`.
- Chat turns are captured to `memory_pages` (`source="chat"`,
  `page_type="conversation"`, background helper in `agent_routes.py`) and
  recalled into agent prompts via `BaseAgent._render_memories_context`
  (ADR-014) — embedding-only, no per-turn LLM calls.

## Testing tiers — `apps/api/tests/` (Phase 0)

`unit/` (no services; conftest supplies env), `regression/` (one per fixed bug),
`live/` (`@pytest.mark.live`, needs `./start.sh`; wraps the 13 standalone
`test_*.py` scripts). `pytest` = unit tier; `pytest -m live` = full stack;
`turbo test` from the monorepo root; CI runs the unit tier. Contract:
[standards/testing.md](../standards/testing.md).

## Background work & scheduling

- **Celery** (`celery_app.py`) — Redis broker, queues `default`, `agents`,
  `orchestrator`; long orchestrations run async with status polling
  (`queue_routes.py`).
- **APScheduler** (`scheduler.py`) — cron jobs, e.g. weekly plan generation
  Monday 08:00 IST.

## Data model — `app/models.py`, `planner_models_db.py`, `app/state/models.py`

40 ORM tables (+3 non-ORM research tables kept for prod parity). Load-bearing ones:

- `users` (Clerk auth + subscription), `founder_profiles` (business context).
- `agents` (registry: name, system_prompt, model, capabilities),
  `user_agent_configs` (per-user overrides).
- `tasks`, `task_feedback` (learning loop), `workflow_templates`, `workflows`,
  `workflow_executions` (approval gate lives in `tasks.requires_approval` +
  `step_state`).
- `knowledge_items` (pgvector RAG), `memory_pages`/`memory_links` (temporal KG;
  SQL fn `memory_temporal_score` is load-bearing), `planner_users`/`plan_history`.
- State Engine (ADR-009): `state_sources`, `state_observations`,
  `company_state_entities`, `state_relations`.

**Bootstrap = `alembic upgrade head` — the single path** (ADR-011). The re-rooted
chain `0000_baseline → 0001_workflow_engine → 0002_state_engine` builds the full
schema on an empty pgvector Postgres: extensions, all tables + indexes, the
`update_updated_at_column` triggers, `memory_temporal_score`, views and the
`workflow_templates`/`subscription_plans` seeds (`agents` rows come from
`sync_agents_to_db` at startup, ADR-004). `schema.sql` is the human-readable
**secondary** artifact only — never applied by any pipeline; the old
`migrations/*.sql` files are absorbed into the baseline and deleted. CI's
`migrations` pytest tier asserts ORM↔schema name-level parity at head on every
push. Any **new model module must be imported in `alembic/env.py`** (and in
`tests/migrations/test_schema_baseline.py`), or autogenerate and the parity test
both go blind to it.

Schema changes go through **Alembic** (`apps/api/alembic/`), not hand-edited SQL.

## Frontend — `apps/web`

App Router with route groups: `(auth)`, `(dashboard)`, `(onboarding)`. Dashboard
pages: overview, chat (SSE streaming), agents (live status), planner, tasks,
knowledge, memory, content-ideas, settings. Shared client utilities in `lib/`:
`useApi` (stable, ref-based token), `useEventSource` (SSE with backoff),
`useStreamingFetch` (POST-based SSE for chat). See [standards/coding.md](../standards/coding.md).

**Chat state is layout-scoped, not page-scoped.** `lib/chat-store.tsx`
(`ChatProvider`, mounted in the `(dashboard)` layout) owns every chat session —
the orchestrator Chat page and the per-agent chat panels — including in-flight
SSE fetches, so navigating between tabs never aborts a running agent chat; the
sidebar shows a pulse dot on Chat/Agents while a run is in flight. Pages are
thin views over `useChatStore()`. The provider also restores persisted history
per session and, after a reload that lands mid-run, briefly polls history until
the assistant reply arrives.

## Infrastructure

Docker Compose: `pgvector/pgvector:pg16` + `redis:7-alpine`. CORS middleware on
the API for the Clerk frontend. Config via `pydantic-settings` (`config.py`) from
`apps/api/.env` and `apps/web/.env.local`.
