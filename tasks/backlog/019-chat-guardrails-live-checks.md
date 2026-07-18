---
id: 019
title: Live-LLM checks for chat guardrails (deferred Tier B of task 017)
status: backlog
created: 2026-07-18
dependencies: [017]
links:
  - tasks/completed/017-agent-history-replay-fix-guardrails.md
  - docs/decisions.md   # ADR-013
---

# 019 — Live-LLM checks for chat guardrails

Task 017 shipped the history-as-context fix + universal guardrails with unit
coverage only (AC-1..8). Three acceptance criteria need a **live LLM** and were
deferred (laptop cannot run Ollama; EC2 is free-tier, smoke-checks only):

- **AC-9** Resumed session: agent answers only the new question — no re-answering
  of the prior turn.
- **AC-10** Off-topic request → brief decline + redirect to what the agent can do.
- **AC-11** Follow-up continuity: references to earlier turns resolve correctly
  ("expand point 2 from before").

## How to run

Fold into the next release smoke on the deployed env (workflows/release.md), or a
one-off manual session against the EC2 deployment: one resumed session covering
all three checks, transcript recorded in `reports/`. Success metric from 017:
0 re-answered questions across a 5-session resumed-chat smoke; `tokens_used` per
resumed turn lower than pre-017 baseline.
