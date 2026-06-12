---
id: 007
title: Agent Evolution — feedback → behavior loop
status: backlog
stage: product
owner: eng-product
created: 2026-06-10
dependencies: [001]
links: [docs/agent-evolution.md, docs/decisions.md]
---

# 003 — Feedback → behavior loop

## Objective
Close the loop so agents adapt from feedback. Today `task_feedback`/`agent_analytics`
are write-only and `LearningInsight` is never written (no feedback→behavior path).

## Scope sketch (design: docs/agent-evolution.md §1)
- On `task_feedback` submit, run `ProfileIntelligence.extract_insights`; synthesize into
  `UserProfileIntel.conversation_guide` (already injected by `base.py`).
- Populate `LearningInsight` from low-rating patterns; surface to the task-001
  `SpecializationEngine` as human-approved overlay updates.

## Acceptance criteria (to refine at Analyze)
- [ ] Feedback produces insights → updated profile → changed next-run prompt (test).
- [ ] No ungated change to agent behavior (human approval preserved).

> Reuse: `app/agents/profile_intelligence.py`, `SpecializationEngine` (task 001),
> `app/api/task_review_routes.py:452`.
