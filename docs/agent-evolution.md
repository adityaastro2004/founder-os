# Agent Evolution Architecture — design & roadmap

> Target architecture for turning Founder OS's product agents into founder-specific
> strategic systems that get smarter as founder context accumulates. Task 002
> (strategic prompt upgrade + code→DB sync) shipped the foundation; the subsystems
> below are **designed here and queued** as their own workflow tasks. Each section:
> current state → target → the backlog task that builds it.

## The loop we're building toward

```
Founder context → Organizational understanding → Agent evolution → Better decisions → Better outcomes
        ▲                                                                                   │
        └──────────────────────────  feedback closes the loop  ◄────────────────────────────┘
```

Shipped (task 002): code is the source of truth for agent prompts (synced to DB at
startup), and every agent now reasons in systems and specializes to the injected
founder context (`<founder_profile>`, `<user_profile>`, `<user_custom_instructions>`,
memory — see `app/agents/base.py:340-480`). Per-founder overlays exist via the
specialization engine (task 001).

**Shipped (task 003 — the Agent Evolution Engine):** `Founder Context Model` +
`Agent Generator` regenerate each agent's *full definition* per founder (system prompt
+ decision framework + tool selection), versioned + approval-gated; the registry serves
the active per-user definition over the global agent (proven against the live DB). This
closes #1 deeply and starts #2. See ADR-006, `app/agents/context_model.py`,
`app/agents/generator.py`. Remaining gaps below.

## 1. Feedback → behavior loop  →  task 003

- **Current:** `task_feedback`, `agent_analytics`, `learning_insights` are
  write-only/unused; `LearningInsight` is never written. Feedback never changes future
  behavior (Explore-confirmed).
- **Target:** close the loop — on feedback, extract insights
  (`ProfileIntelligence.extract_insights`), synthesize into `UserProfileIntel`
  (`conversation_guide`), which `base.py:_load_user_profile_context` already injects;
  populate `LearningInsight` from low-rating patterns and surface to the
  specialization engine (task 001) as proposed overlay updates (human-approved).
- **Reuse:** `profile_intelligence.py`, the task-001 `SpecializationEngine`,
  `task_review_routes.py:452`.

## 2. Founder-memory evolution (temporal graph → prompts)  →  task 005

- **Current:** the temporal knowledge graph (`memory_pages`/`memory_links`,
  composite-scored recall) is a standalone REST API; **not injected** into agent
  prompts. ProfileIntelligence synthesis is on-demand only.
- **Target:** inject top composite-scored `memory_pages` into `base.build_context`;
  define a synthesis cadence (every N interactions). Agents recall relevant founder
  history automatically.
- **Reuse:** `app/memory/manager.py`, `app/agents/memory.py:build_context`.

## 3. Workflow execution engine  →  task 004

- **Current:** `workflow_templates`/`workflows`/`workflow_executions` tables exist but
  there is **no engine** — pure scaffolding.
- **Target:** a `WorkflowEngine` that parses `steps` JSONB and runs them via the
  Orchestrator/router, with `WorkflowExecution` state tracking and the existing
  approval gate. Founder supervises; system executes (Level-3 orchestration applied to
  the product).
- **Reuse:** `orchestrator.py` delegation, `router.py`, `approval.py`, the
  scheduler (`scheduler.py`) for triggers.

## 4. Reasoning scaffolding (plan / reflect)  →  task 006

- **Current:** `ExecutionEngine.run` is a plain LLM→tools loop; no explicit
  plan/reflect step.
- **Target:** optional pre-execution **plan** and post-execution **reflect** hooks so
  agents validate output against the founder's goal before returning. Capture decision
  reasoning into the trace.
- **Reuse:** `execution.py` loop; the Decision Framework already in every prompt
  (task 002) gives the LLM the structure to plan/reflect against.

## 5. Agent communication / dependency DAG  →  (future)

- **Current:** Orchestrator chains delegations via shared memory; no dependency DAG,
  no auto-parallelization, no decision-reason capture.
- **Target:** represent a plan as a task DAG; auto-parallelize independent branches;
  record why each agent was chosen. Builds on the workflow engine (task 004).

## Sequencing rationale

003 (feedback) and 005 (memory injection) are the highest-leverage, lowest-risk —
they close the founder-adaptation loop using existing storage. 004 (workflow engine)
and 006 (reasoning scaffolding) are larger and depend on 003/005 proving value first.
See [roadmap.md](roadmap.md); decisions in [decisions.md](decisions.md) (ADR-004/005).
