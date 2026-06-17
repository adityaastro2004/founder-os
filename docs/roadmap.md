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

- _(seed)_ **Establish the development factory** — the meta-layer in this repo so
  the system improves itself. Why: less founder context-repetition, higher quality.
  Status: `now`.

## Next

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

## Later

- **Agent Evolution — workflow execution engine** (task 004): wire the unused
  `workflow*` tables into a real engine. See [agent-evolution.md](agent-evolution.md) §3.
- **Agent Evolution — reasoning scaffolding** (task 006): plan/reflect hooks in
  `ExecutionEngine`. See [agent-evolution.md](agent-evolution.md) §4.
- **Adopt a real test framework** (pytest + pytest-asyncio backend, Vitest frontend)
  and a `turbo test` task. Why: current standalone `test_*.py` scripts don't scale.
  See [standards/testing.md](../standards/testing.md).
- **Replace tool stubs** — implement `web_search` (Tavily/SerpAPI) and real
  `get_business_metrics`. Why: agents currently ground on mock data.
  See [docs/requirements.md](../docs/requirements.md) (known gaps).

## Backlog / ideas

- _(unvetted ideas land here for the product agent to prioritize)_

---

## Shipped

| Date | Item | Task |
|------|------|------|
| 2026-06-10 | Founder-aware agent specialization (Evolution Engine MVP) | [tasks/completed/001](../tasks/completed/001-founder-aware-agent-specialization.md) |
| 2026-06-10 | Strategic systems-thinking prompts + code→DB sync (agents now run rich prompts) | [tasks/completed/002](../tasks/completed/002-agent-strategic-prompt-upgrade.md) |
| 2026-06-11 | Agent Evolution Engine — per-founder definition regeneration (Context Model + Generator) | [tasks/completed/003](../tasks/completed/003-agent-evolution-engine.md) |
| 2026-06-11 | Production hardening — 10 bug classes fixed; agents+RAG+A2A proven live (RAG 16/16, A2A delegation, memory ALL, units 120/120) | [tasks/completed/008](../tasks/completed/008-prod-hardening-core.md) |
| 2026-06-12 | PDF → RAG ingestion + blank-only primary_goal auto-fill (live-verified; + fixed a BackgroundTasks request-rollback bug) | [tasks/completed/009](../tasks/completed/009-pdf-rag-goal-autofill.md) |
| 2026-06-12 | Knowledge tab File/PDF upload UI (+ apiFetch FormData fix) | [tasks/completed/010](../tasks/completed/010-knowledge-tab-file-upload.md) |

> Known technical-debt items live alongside the roadmap so prioritization sees the
> full picture. Significant architectural choices are recorded in
> [decisions.md](decisions.md).
