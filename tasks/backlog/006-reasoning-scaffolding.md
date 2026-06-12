---
id: 006
title: Agent Evolution — reasoning scaffolding (plan / reflect)
status: backlog
stage: product
owner: eng-product
created: 2026-06-10
dependencies: [002]
links: [docs/agent-evolution.md, docs/decisions.md]
---

# 006 — Reasoning scaffolding

## Objective
`ExecutionEngine.run` is a plain LLM→tools loop with no explicit plan/reflect step.
Add optional pre-execution **plan** and post-execution **reflect** hooks so agents
validate output against the founder's goal before returning, and capture decision
reasoning into the trace.

## Scope sketch (design: docs/agent-evolution.md §4)
- `before_execute` (plan) and `after_execute` (reflect) hooks in `ExecutionEngine`.
- Use the Decision Framework already in every prompt (task 002) as the structure.

## Acceptance criteria (to refine at Analyze)
- [ ] Plan/reflect hooks invoked; reasoning captured in the trace (test, mock LLM).
- [ ] Opt-in per agent; no latency/cost regression when disabled.

> Reuse: `app/agents/execution.py`. Larger task — sequence after 003/005.
