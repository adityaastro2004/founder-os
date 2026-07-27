# LangGraph Orchestrator — Design Spec

- **Date:** 2026-07-27
- **Status:** Approved (brainstorming complete)
- **Scope:** Replace the orchestrator's control loop with a LangGraph `StateGraph`;
  keep every specialist agent, tool, memory layer, event bus, and the 3-tier LLM
  provider fallback unchanged.
- **Related:** [orchestrator.py](../../../founder-os/apps/api/app/agents/orchestrator.py) ·
  [base.py](../../../founder-os/apps/api/app/agents/base.py) ·
  [router.py](../../../founder-os/apps/api/app/agents/router.py) ·
  [execution.py](../../../founder-os/apps/api/app/agents/execution.py) ·
  ADR to be added in [decisions.md](../../decisions.md)

---

## 1. Motivation

The current orchestrator ([orchestrator.py](../../../founder-os/apps/api/app/agents/orchestrator.py))
is an LLM loop that exposes specialists as a `delegate_task` tool and lets the model
decide routing. It works, but has three limits this design removes:

1. **No durability.** The loop lives and dies with the HTTP request
   ([execution.py:18](../../../founder-os/apps/api/app/agents/execution.py#L18) — an
   in-memory `while not done`). A deploy, crash, or timeout mid-run loses all
   completed specialist work and re-pays for it on retry.
2. **No human-in-the-loop that survives a session.** The approval gate exists but
   cannot pause a run for hours and resume it across a restart.
3. **Every routing decision costs main-model tokens.** The orchestrator LLM reads
   the full prompt and emits a `delegate_task` call on every round (often 3–5 rounds
   for a complex request).

LangGraph gives us exactly three primitives to fix these — `StateGraph` (structured
routing), `AsyncPostgresSaver` (durable checkpoints), and `interrupt()` (pause /
resume) — **without** adopting LangChain chat models. Nodes are plain async
functions that call our existing code, so the provider fallback in
[llm.py](../../../founder-os/apps/api/app/agents/llm.py) and every specialist agent
survive intact.

**Non-goals:** migrating specialist agents to graphs; replacing `BaseAgent` /
`ExecutionEngine` for non-orchestrator agents; adopting LangChain models; changing
the web UI or its SSE event contract.

---

## 2. Rollout decision

**In-place replacement** (chosen by the founder over a feature flag). The current
`OrchestratorAgent` control loop is replaced by the graph; there is no runtime
legacy fallback.

Consequence: **no instant rollback lever.** The mitigation is a **parity test suite**
(§7) that must be green before merge, plus the legacy loop remaining recoverable via
git history. The PR stays small and reviewable.

---

## 3. Architecture

Only three imports come from LangGraph: `StateGraph`, `AsyncPostgresSaver`,
`interrupt`. Everything under a node is existing Founder OS code.

```
StateGraph(OrchestratorState)  [checkpointer = AsyncPostgresSaver]

  classify ── cheap-tier LLM ──▶ {intent, planned_agents, needs_approval}
     │
     │  conditional edges (plain Python, 0 tokens)
     ▼
  ┌── planner_node   ─▶ PlannerAgent.run()     (unchanged)
  ├── research_node  ─▶ ResearchAgent.run()    (unchanged)
  ├── content_node   ─▶ ContentAgent.run()     (unchanged)
  └── support_node   ─▶ SupportAgent.run()     (unchanged)
     │   (each writes into results, emits the same event-bus events)
     ▼
  approve? ── interrupt() ──▶ [persist + return; resume later]
     │
     ▼
  hydrate_context ── refresh volatile company/task state ──▶
     │
     ▼
  synthesize ── main-tier LLM (once) ──▶ final_answer
```

The routing intelligence that was an LLM tool-call becomes: **one cheap classify
call + deterministic conditional edges.** Ambiguous requests have an escape hatch
(§5).

### Module layout

New package `app/agents/graph/` (additive; does not disturb sibling agent files):

```
app/agents/graph/
  __init__.py
  state.py           # OrchestratorState TypedDict
  nodes.py           # classify, specialist wrappers, hydrate_context, synthesize
  edges.py           # routing functions for conditional edges
  orchestrator_graph.py  # builds + compiles the StateGraph, owns the checkpointer
  context.py         # snapshot + hydrate helpers (reuse base.py context loaders)
```

`OrchestratorAgent.run()` becomes a thin adapter that builds initial state, invokes
the compiled graph with a `thread_id`, and maps the final state back to `AgentResult`
(preserving `delegations` / `OrchestrationTrace` shape for existing callers).

---

## 4. State model

The graph state mirrors the **full** context surface base.py injects today
([base.py:389-481](../../../founder-os/apps/api/app/agents/base.py#L389)), not just
profile. This was a correction during design review: routing and synthesis must see
company + task + recalled memory, not the founder profile alone.

```python
class OrchestratorState(TypedDict):
    user_id: str
    session_id: str
    user_input: str
    query_embedding: list[float] | None   # reused for on-demand recall mid-graph

    # ── context surface (mirrors base.py) ──
    profile_context: str    # founder profile
    company_context: str    # <founder_business_context> + State Engine snapshot:
                            #   goals / projects / active tasks (the moat)
    task_context: str       # current_plan, last_orchestration, research_findings
                            #   (from shared/working memory)
    memory_context: str     # <memories> cross-session semantic recall
    extra_context: str      # passthrough from the API (extra_context param)

    # ── working state (accumulates across nodes → cheap resume) ──
    intent: str             # SIMPLE | MULTI_STEP | COMPLEX
    planned_agents: list[str]
    results: dict[str, str] # agent_name -> output; checkpointed, never re-paid
    needs_approval: bool
    approval_answer: str | None   # filled on resume
    final_answer: str
    trace: list[dict]       # feeds the event bus + OrchestrationTrace parity
```

`results` accumulating in state is what makes crash-resume cheap: a completed
specialist's output is in the checkpoint, so resume never re-runs or re-pays for it.

---

## 5. Nodes & edges

- **`classify`** — one call to a **cheap tier** (Ollama default; Groq / Gemini-flash
  when configured) returning structured `{intent, planned_agents, needs_approval}`.
  Reads `company_context` + `task_context` so routing reflects what the company is
  actually working on. Replaces today's main-model routing decision.
- **Conditional edges** (`edges.py`) — plain functions reading
  `state["planned_agents"]` fan out to specialist nodes. **Zero tokens.** This is the
  "routing through logic and state" goal.
- **Specialist nodes** — thin wrappers over the existing `agent.run()` via the
  router/registry. Write output into `results`; emit the **same** event-bus events
  (`delegation.starting/executing/completed/failed`) the orchestrator emits today.
- **Escape hatch** — when `classify` returns `intent = COMPLEX` (genuinely
  ambiguous), route to an `llm_route` node that does a full LLM routing decision.
  Keeps quality on hard cases without paying routing tokens on easy ones.
- **`hydrate_context`** — refreshes volatile company/task context before synthesis
  (see §6).
- **`synthesize`** — one **main-tier** LLM call combining `results` into the final
  answer, following the existing Phase-4 synthesis rules (lead with the answer, weave
  specialist insight, list actions, end with Next Steps). Has access to a
  `fetch_context(topic)` tool for on-demand recall.

**Expected token profile.** Today: main-model routing + N re-delegation rounds.
New: **1 cheap classify + 1 main synthesize**, routing free in between. Specialist
calls themselves are unchanged. (Escape-hatch COMPLEX requests add one routing call —
still bounded, and only on hard cases.)

---

## 6. Durability (both crash-resume and human-in-the-loop)

- **Checkpointer:** `AsyncPostgresSaver` on the existing Postgres 16. LangGraph
  manages its **own** tables (`checkpoints`, `checkpoint_writes`, …) via its
  `.setup()` — outside our SQLAlchemy models. Per repo rule #8 (schema changes go
  through Alembic), the `setup()` DDL is wrapped in an **Alembic migration** so the
  tables are tracked, not created ad-hoc at runtime.
- **`thread_id` = `session_id`** (falling back to a generated `run_id`) — the
  checkpoint key.
- **Crash-resume:** on restart, re-invoke the graph with the same `thread_id`;
  LangGraph replays from the last completed node using checkpointed `results` — no
  specialist re-runs.
- **Human-in-the-loop:** the `approve?` node calls `interrupt()`; the graph persists
  and the request returns. A new `POST /orchestrate/resume` endpoint feeds
  `approval_answer` back in and continues. Ties into the existing 3-tier approval
  gate and `ask_user_clarification`.

### Stale-context policy (introduced by durability)

A run may checkpoint, pause for approval, and resume hours later — a snapshotted
`company_context` / `task_context` can be out of date (a task completed, a plan
changed). Policy:

- **Snapshot at `classify` time** — routing only needs a point-in-time read.
- **Re-hydrate volatile context on resume and before `synthesize`** — the
  `hydrate_context` node re-pulls current State Engine + shared memory so the final
  answer reflects *now*. Profile (near-immutable) is trusted from the checkpoint;
  company/task state is refreshed.
- **On-demand fetch** — a `fetch_context(topic)` tool available to `synthesize` (and
  specialists) pulls fresh memory / State-Engine data when the snapshot doesn't cover
  something, using the stored `query_embedding` for recall.

---

## 7. Streaming / UI contract (hard constraint)

The web UI consumes `orchestration.started`, `delegation.executing`,
`delegation.completed`, etc. over SSE
([agent_routes.py:797](../../../founder-os/apps/api/app/api/agent_routes.py#L797);
background-chat architecture). **The event contract is preserved byte-for-byte.**
LangGraph's own streaming is additive — every node still publishes to the Redis event
bus exactly as today. The UI does not change. This is a parity assertion in tests.

---

## 8. Testing (the safety net that replaces the flag)

Because rollout is in-place, tests carry the rollback risk:

- **Parity fixtures** — ~10 representative requests (simple, multi-step, complex,
  approval-needed). Assert equivalent agent selection, a coherent synthesized answer,
  and the same event sequence as the legacy loop.
- **Durability tests** — kill mid-run then resume (assert no specialist re-runs);
  interrupt at approval then resume with an answer.
- **Stale-context test** — mutate company/task state during a paused run; assert
  `synthesize` reflects the refreshed state, not the snapshot.
- **Regression tier** — existing orchestrator tests updated to the new entry point.
- Gates: `pytest` unit + `pytest -m migrations` (checkpointer migration) green before
  merge; the standard `ci-success` check.

---

## 9. Risks & mitigations

1. **In-place = no instant rollback.** → Parity suite green before merge; legacy loop
   recoverable via git; small reviewable PR.
2. **New heavy dependency.** `langgraph` + `langgraph-checkpoint-postgres` pull in
   `langchain-core` (transitively) and `psycopg`. → CodeQL / dependency-review scan
   it; pin versions; document in requirements.txt.
3. **Deterministic routing is dumber than LLM routing** on ambiguous asks. →
   `intent = COMPLEX` escape hatch to full LLM routing (§5).
4. **`psycopg` vs `asyncpg`.** The checkpointer uses psycopg3, not the app's asyncpg.
   → A separate checkpointer connection/pool, configured from the same `DATABASE_URL`;
   documented in DEPLOY.md.

---

## 10. Success criteria

- Orchestration runs on the LangGraph `StateGraph` in-place.
- A run interrupted by a restart resumes without re-running completed specialists.
- A run can pause at approval and resume across sessions via `/orchestrate/resume`.
- Complex requests cost fewer orchestrator LLM tokens than the legacy loop
  (1 cheap classify + 1 synthesize vs. N main-model rounds), measured on the parity
  fixtures.
- The SSE event contract is unchanged; the web UI works without modification.
- All quality gates (§8) pass.
