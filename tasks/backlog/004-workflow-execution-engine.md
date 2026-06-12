---
id: 004
title: Agent Evolution — workflow execution engine
status: backlog
stage: product
owner: eng-product
created: 2026-06-10
dependencies: []
links: [docs/agent-evolution.md, docs/decisions.md]
---

# 004 — Workflow execution engine

## Objective
Wire the unused `workflow_templates`/`workflows`/`workflow_executions` tables into a
real engine so recurring multi-agent processes run under founder supervision.

## Scope sketch (design: docs/agent-evolution.md §3)
- `WorkflowEngine` parses `steps` JSONB → runs via Orchestrator/router with
  `WorkflowExecution` state tracking and the existing approval gate.
- Triggers via `scheduler.py`. Founder supervises; system executes.

## Acceptance criteria (to refine at Analyze)
- [ ] A template can be instantiated and executed end-to-end with state tracking.
- [ ] HIGH-risk steps remain approval-gated.

> Reuse: `orchestrator.py`, `router.py`, `approval.py`, `scheduler.py`. Larger task —
> sequence after 003/005 prove value.
