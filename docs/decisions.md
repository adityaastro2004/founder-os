# Architecture Decision Records — Founder OS

> A running log of significant technical decisions and their rationale, so the
> system never re-litigates a settled question or loses the "why". The
> [architect agent](../agents/architect.md) appends an ADR whenever a decision
> shapes the architecture. Newest first.

## Format (one entry per decision)

```
## ADR-NNN — <short title>
- Date: YYYY-MM-DD
- Status: proposed | accepted | superseded by ADR-MMM
- Context: what forced a decision (the problem, constraints).
- Decision: what we chose.
- Consequences: trade-offs, what this rules out, follow-ups.
- Links: tasks/, code, related ADRs.
```

---

## ADR-007 — One real user identity everywhere (no synthetic uuid5 keys)

- Date: 2026-06-11
- Status: accepted (shipped — task 008)
- Context: routes derived a synthetic `uuid5("clerk:<id>")` UUID never inserted into
  `users`; FK-constrained inserts (knowledge_items, tasks, …) 500'd for any user who
  hadn't onboarded, and reads/writes could disagree on the key. Verified live
  (`knowledge_items_user_id_fkey` violation; RAG stored nothing).
- Decision: all identity resolution goes through `app/users.py:get_or_create_user_id`
  (select → race-safe `INSERT … ON CONFLICT DO NOTHING` → select), creating a minimal
  users row on first sight (same semantics as onboarding). Applied across knowledge,
  agent, task-review, approval, activity routes and Celery agent tasks; activity event
  filtering keeps legacy uuid5 aliases so historical events still match.
- Consequences: RAG/tasks/approvals work pre-onboarding; one key for reads and writes;
  approvals created during agent runs are visible in the approval endpoints. Trade-off:
  helpers that lacked a db dependency open a short-lived session (acceptable; flagged
  for later consolidation).
- Links: [tasks/completed/008](../tasks/completed/008-prod-hardening-core.md), `app/users.py`.

## ADR-006 — Agent Evolution Engine: per-founder definition regeneration

- Date: 2026-06-11
- Status: accepted (shipped — task 003)
- Context: task 001 only *overlaid* per-founder `custom_instructions`; the founder wanted
  real evolution — agent *definitions* that differ per founder and regenerate as context
  grows. The global `agents` row is shared by all users, so per-founder definitions need
  separate, versioned storage applied at runtime.
- Decision: two new tables (`founder_context_models`, `agent_definitions`) — ORM +
  `schema.sql` DDL, **no Alembic** (the repo's `versions/` is empty; schema is managed
  via `schema.sql` + a one-time apply). A `FounderContextModelBuilder` distills
  `FounderProfile` + `UserProfileIntel` into a structured, hashed, versioned model
  (only re-versions on real change). An `AgentGenerator` regenerates each agent's full
  definition (system_prompt + decision_framework + selected_tools ⊆ the real tool menu)
  from (role spec + context model), staged `proposed`. Approval makes it `active` and
  supersedes the prior active row; `registry.get()` prefers the active per-user
  definition over the global `agents` row (base.py unchanged). Onboarding triggers it in
  the background (superseding task-001's overlay trigger; the specialize endpoints remain
  for manual tweaks).
- Consequences: genuine per-founder agents (proven against the live DB — registry serves
  the regenerated prompt). Approval-gated, versioned + reversible (rollback), bounded
  (N calls per context change). Trade-off: full behavior regeneration is sensitive →
  hard human-in-the-loop, never auto-activated. Out of scope (queued): continuous
  auto-evolution from memory/feedback (#4), dynamic NEW sub-agents (#3).
- Links: [tasks/completed/003](../tasks/completed/003-agent-evolution-engine.md),
  `app/agents/context_model.py`, `app/agents/generator.py`,
  `app/agents/registry.py` (`_load_active_definition`), `app/api/evolution_routes.py`.

## ADR-005 — Strategic systems-thinking prompt architecture

- Date: 2026-06-10
- Status: accepted (shipped — task 002)
- Context: the product agents ran as generic task executors; the founder wants
  founder-specific strategic systems-thinkers (Planner→CSO, Research→Market
  Intelligence, Product→Strategist/Architect, Content→Narrative Architecture,
  Ops→Operating-System Architect).
- Decision: a shared `app/agents/strategy.py` defines a `SYSTEMS_THINKING_PREAMBLE`
  (systems/incentives/constraints/feedback-loops/tradeoffs/first-principles + a
  5-point Decision Framework + an instruction to specialize to the injected founder
  context) and `strategic_header(role, charter)`. This is **prepended** to each
  agent's existing prompt — operations (tool protocols, calendar-intent rules, content
  formats) are preserved; strategy is layered on. Agents reference the founder context
  already injected by `base.py:340-480`.
- Consequences: low regression risk (operational instructions intact; e2e 50/50);
  one shared standard all agents follow; per-agent diff is a single prepend. Larger
  adaptation subsystems are designed in [agent-evolution.md](agent-evolution.md) and
  queued (tasks 003-006).
- Links: [tasks/completed/002](../tasks/completed/002-agent-strategic-prompt-upgrade.md),
  `app/agents/strategy.py`.

## ADR-004 — Code is the source of truth for agent definitions (synced to DB)

- Date: 2026-06-10
- Status: accepted (shipped — task 002)
- Context: rich agent prompts live in Python (`AGENT_CLASSES`), but runtime prefers
  the DB value (`base.py:351`), and the `agents` rows were seeded with **generic**
  prompts (schema.sql / migration). With no code→DB sync, the rich prompts were dead
  code — agents ran generic prompts (verified against the live DB).
- Decision: add `sync_agents_to_db` (registry.py), called at startup in the lifespan
  (`main.py`), which **upserts** each `AGENT_CLASSES` entry's prompt/capabilities/tools
  into its `agents` row. Code becomes the source of truth; the DB is a synced cache.
  `base.py:351` is left unchanged (DB still authoritative at runtime, so admin DB edits
  remain possible between deploys).
- Consequences: the rich/strategic prompts now actually run; idempotent; no schema
  migration. Trade-off: startup sync overwrites manual DB prompt edits — acceptable
  (manual prompt editing isn't a current workflow). Best-effort: a sync failure logs
  but does not block startup.
- Links: [tasks/completed/002](../tasks/completed/002-agent-strategic-prompt-upgrade.md),
  `app/agents/registry.py` (`sync_agents_to_db`), `app/main.py`.

## ADR-003 — Founder-aware agent specialization via `is_enabled` staging

- Date: 2026-06-10
- Status: accepted (shipped — task 001, 13/13 tests pass)
- Context: the product should ship agents specialized to each founder (the "Agent
  Evolution Engine" vision), but runtime per-user config application **already
  exists** (`registry.py:236`, `base.py:364`) and the MVP must avoid a schema
  migration and keep a human-approval guarantee.
- Decision: generate per-agent specialization from `FounderProfile` via one LLM call
  per active agent, and **stage proposals as `UserAgentConfig` rows with
  `is_enabled=False`** (invisible to the runtime loader, which filters
  `is_enabled == True`). Founder approval flips the row to `True`. Use explicit
  propose→approve **endpoints** as the gate rather than the tool `ApprovalGate`
  (which gates tool calls inside an agent run, not onboarding-time proposals).
- Consequences: no migration; reuses the existing apply path (verify-only);
  human-in-the-loop preserved. Trade-off: `is_enabled=False` overloads "proposed" and
  "user-disabled" — accepted for MVP; a dedicated `status` column is a later increment
  if the meanings need to diverge. Cost bounded to N active agents per profile change
  (explicitly **not** per task — the literal "redesign before every task" was rejected).
- Links: [tasks/active/001-founder-aware-agent-specialization.md](../tasks/active/001-founder-aware-agent-specialization.md).

## ADR-002 — Engineering meta-layer as the development "factory"

- Date: 2026-06-10
- Status: accepted
- Context: every session started cold and re-derived stack, conventions, and
  workflow; the founder repeatedly re-explained context.
- Decision: add a self-improving meta-layer (this `docs/`, `standards/`, `agents/`,
  `skills/`, `workflows/`, `meta/`, `tasks/`, `reports/`) governed by
  [CLAUDE.md](../CLAUDE.md), with engineering agents named distinctly (`eng-`) from
  the product's runtime agents.
- Consequences: durable context + repeatable workflows; small upkeep cost (keep
  docs in sync as the last workflow step). Adopted the blueprint vocabulary
  (executor/qa, product/security agents, state-folder tasks).
- Links: this whole meta-layer; [CLAUDE.md](../CLAUDE.md).

## ADR-001 — Pre-existing product architecture (baseline, recorded)

- Date: (pre-existing)
- Status: accepted
- Context: the product needs a multi-agent backend a solo founder can run locally.
- Decision: single Orchestrator (Stripe-Minions, agents-as-tools); FastAPI + async
  SQLAlchemy + Postgres/pgvector + Redis + Celery + APScheduler; Clerk JWT auth;
  3-tier approval gate; pluggable LLM provider with fallback (Ollama default);
  Next.js 16 dashboard. Details in [architecture.md](architecture.md).
- Consequences: OSS/local-first, no vendor lock-in; provider neutrality and the
  approval gate are load-bearing invariants. Recorded here as the baseline so future
  ADRs can reference and supersede specific choices.
- Links: [architecture.md](architecture.md), [vision.md](vision.md).
