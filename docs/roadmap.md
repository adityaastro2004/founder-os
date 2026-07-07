# Roadmap — Founder OS

> The prioritized "what's next" for the product. Owned by the
> [product agent](../agents/product.md); updated as the **last step** of every
> major task (see [CLAUDE.md](../CLAUDE.md) §7, step 8). Keep it honest — it's the
> single place that answers "is this the highest-value thing to build now?".

## How to use this file

- Each item: a one-line outcome, a **why** (user value), and a status.
- Status: `now` (in flight) · `next` (committed, not started) · `later` (intended) ·
  `idea` (unvetted) · `done`.
- When work completes, move the item to **Shipped** with a date and link the task.
- New ideas land in **Backlog / ideas** until the product agent vets them.

## Now

- **Full-system revamp (founder-approved 2026-07-03):** six sequential phases, each
  with its own design → plan → build cycle. See the
  [Phase 0 spec](superpowers/specs/2026-07-03-phase0-foundation-revamp-design.md)
  for the decomposition rationale.

  | Phase | Outcome | Status |
  |-------|---------|--------|
  | 0 | Foundation revamp — audit → repair → reshape (task 012) | `done` (2026-07-03) |
  | 1 | State Engine core + Obsidian sync (task 011) | `done` (2026-07-07) |
  | 2 | Notion adapter (same engine/ABC) | `next` |
  | 3 | Hermes skills feed (`system` feed) | `later` |
  | 4 | Paperclip (paperclip.ing) via MCP | `later` |
  | 5 | Deployment — Docker images + runbook | `later` |

- **Company State Engine — the moat (flagship, task 011):** a canonical, living model of
  the company (goals · projects · tasks · decisions · metrics · people · meetings) fed by
  passive multi-channel observation and surfaced where the founder already works. Wrapped in
  the five loops (Observe → Remember → Understand → Execute → Learn). Why: fragmentation /
  app-switching is the deepest, most defensible founder pain — no tool today *knows the
  company*. **Slice 1** = State Engine core + **Obsidian** bidirectional sync (local-first,
  no OAuth), proving Observe→Remember→Sync end-to-end. Status: `now`. See ADR-009 +
  [tasks/backlog/011](../tasks/backlog/011-company-state-engine.md) +
  [spec](superpowers/specs/2026-06-22-company-state-engine-design.md).
- _(seed)_ **Establish the development factory** — the meta-layer in this repo so
  the system improves itself. Why: less founder context-repetition, higher quality.
  Status: `now`.

## Next

- **State Engine — feed 2 (`user_doc`) + feed 3 (`system`):** extend the reconciler so
  founder-provided docs (existing PDF/knowledge ingestion) and system-generated knowledge
  (agent memories + Hermes procedural skills) also emit canonical state entities — each
  provenance-tagged. Why: the founder asked the engine to be updated by both what it learns
  itself and the docs they give it. Builds on task 011 slice 1. Status: `next`.
- **State Engine — hygiene/Curator (anti-bloat):** ship the full hygiene system —
  provenance trust-weighting, decay + composite scoring (reuse `memory_pages`), and a
  periodic **Curator** pass that merges/archives/surfaces entities + Hermes skills. Why:
  keep the engine genuinely useful, never bloated (founder requirement). Write-gate + dedup
  ship in slice 1; this completes #2/#4/#5. Status: `next`. See ADR-009.
- **State Engine — more observation adapters:** GitHub (commits/PRs/issues/CI), then
  Stripe (MRR), Slack, Calendar, Notion. Why: each tool added to the unified model removes
  one more reason to app-switch. Status: `next`.
- **n8n-backed auto-workflow system (now optional, task 004):** founder goal →
  Orchestrator auto-generates a workflow → compiled + pushed to **self-hosted n8n**
  (invisible execution + free visual editor) → runs → results visible in Founder OS, with
  the **approval gate enforced server-side**. Why: dynamic in-process AOV graphs are now the
  default execution model (ADR-009); n8n is repositioned as an *optional, invisible*
  execution backend for founders who want a visible/editable flow — no longer the headline
  differentiator. Ships as a thin vertical slice. Status: `later` (de-prioritized below the
  State Engine). See [tasks/backlog/004](../tasks/backlog/004-n8n-workflow-engine.md) +
  ADR-008/ADR-009.
- **Agent Evolution — continuous auto-evolution (#4):** trigger context-model rebuild +
  regeneration automatically as memory/feedback accumulate (cadence + cost caps), so
  agents self-rewrite without a manual kick. Builds on task 003. Status: `next`.
- **Agent Evolution — dynamic sub-agents (#3):** the generator spins up founder-specific
  specialists (e.g. Product→Pricing Analyst) into the `Agent` table + router per startup
  type. Status: `later` (highest risk). See [agent-evolution.md](agent-evolution.md) §5.
- **Agent Evolution — feedback→behavior loop** (task 003-followup): close
  `task_feedback`→insight→`UserProfileIntel`→prompt; populate `LearningInsight`; feed
  the specialization engine. Highest-leverage adaptation loop. Status: `next`.
  See [agent-evolution.md](agent-evolution.md) §1.
- **Agent Evolution — temporal memory injection** (task 005): inject composite-scored
  `memory_pages` into agent prompts. Status: `next`. See [agent-evolution.md](agent-evolution.md) §2.
- **Agent Evolution Engine — increment 2:** feedback-driven re-tuning (mine
  `task_feedback`/`learning_insights` to refine the specialization overlay). Builds on
  task 001 (overlaps task 003). Status: `next`.
- **Tech-debt (from task 001 review):** promote the private `_get_llm_generate`
  (`profile_routes.py`) to a public helper in `app/agents/llm.py`; reused by
  specialization. Status: `next`.
- **Async interactive plan generation (task 013):** plan gen takes ~486s on local
  ollama (2 sequential 4k-token calls) — move to Celery job + polling. From Phase 0
  audit F1. Status: `next`. See [tasks/backlog/013](../tasks/backlog/013-planner-async-generation.md).
- **Tech-debt (CodeQL, pre-existing):** 8 `py/incomplete-url-substring-sanitization`
  findings in `app/crawler/research.py` (URL allowlist checks by substring — use
  parsed-hostname comparison). Plus ~130 non-security lint alerts (unused imports,
  empty excepts) — sweep opportunistically. Status: `later`.
- **Tech-debt (from Phase 0 security review):** HIGH-risk × `always_deny` yields a
  pending approval card instead of an auto-reject — user asked never to be asked.
  Safe (nothing executes without a human) but noisy. Status: `later`.

## Later

- **Workflow auto-evolution (task 004 follow-on):** generated workflows self-rewrite as
  metrics/integrations/feedback change (the readme's "workflows evolve automatically"
  promise) + conditional/branching logic. Builds on the n8n v1 slice and ties into the
  feedback loop (tasks 003-followup / 007). Status: `later`.
- **Agent Evolution — reasoning scaffolding** (task 006): plan/reflect hooks in
  `ExecutionEngine`. See [agent-evolution.md](agent-evolution.md) §4.
- **Adopt a real test framework** (pytest + pytest-asyncio backend, Vitest frontend)
  and a `turbo test` task. Why: current standalone `test_*.py` scripts don't scale.
  See [standards/testing.md](../standards/testing.md).
- **Replace tool stubs** — implement `web_search` (Tavily/SerpAPI) and real
  `get_business_metrics`. Why: agents currently ground on mock data.
  See [docs/requirements.md](../docs/requirements.md) (known gaps).

## Backlog / ideas

- **Workflow template marketplace** — community-built / shareable generated-workflow
  templates. Unvetted; surfaced as out-of-scope from task 004. Status: `idea`.
- _(unvetted ideas land here for the product agent to prioritize)_

---

## Shipped

| Date | Item | Task |
|------|------|------|
| 2026-07-07 | Phase 1 — Company State Engine slice 1: 4-table canonical state + reconciler (write-gate, dedup, provenance) + Obsidian adapter with jailed bidirectional sync + /api/state; live E2E proven (observe→reconcile→render loop, idempotent) | [tasks/completed/011](../tasks/completed/011-company-state-engine.md) |
| 2026-07-03 | Phase 0 foundation revamp — full-system audit (11 subsystems, live-verified), F1–F3 fixed with regression tests, pytest 3-tier harness + turbo test + CI unit tier, integration adapter framework (ADR-010) with Google Calendar as first adapter | [tasks/completed/012](../tasks/completed/012-phase0-foundation-revamp.md) |
| 2026-06-10 | Founder-aware agent specialization (Evolution Engine MVP) | [tasks/completed/001](../tasks/completed/001-founder-aware-agent-specialization.md) |
| 2026-06-10 | Strategic systems-thinking prompts + code→DB sync (agents now run rich prompts) | [tasks/completed/002](../tasks/completed/002-agent-strategic-prompt-upgrade.md) |
| 2026-06-11 | Agent Evolution Engine — per-founder definition regeneration (Context Model + Generator) | [tasks/completed/003](../tasks/completed/003-agent-evolution-engine.md) |
| 2026-06-11 | Production hardening — 10 bug classes fixed; agents+RAG+A2A proven live (RAG 16/16, A2A delegation, memory ALL, units 120/120) | [tasks/completed/008](../tasks/completed/008-prod-hardening-core.md) |
| 2026-06-12 | PDF → RAG ingestion + blank-only primary_goal auto-fill (live-verified; + fixed a BackgroundTasks request-rollback bug) | [tasks/completed/009](../tasks/completed/009-pdf-rag-goal-autofill.md) |
| 2026-06-12 | Knowledge tab File/PDF upload UI (+ apiFetch FormData fix) | [tasks/completed/010](../tasks/completed/010-knowledge-tab-file-upload.md) |

> Known technical-debt items live alongside the roadmap so prioritization sees the
> full picture. Significant architectural choices are recorded in
> [decisions.md](decisions.md).
