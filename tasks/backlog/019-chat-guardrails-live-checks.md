---
id: 019
title: Live-LLM checks for chat guardrails (deferred Tier B of task 017)
status: backlog
created: 2026-07-18
dependencies: [017, 020]
links:
  - tasks/completed/017-agent-history-replay-fix-guardrails.md
  - docs/decisions.md   # ADR-013, ADR-014
  - tasks/active/020-chat-semantic-memory.md   # scope C extension below
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

## Extension — chat semantic memory checks (task 020 scope C, ADR-014)

Task 020's Tier B was deferred for the same infra reason; fold these into the
same live session:

- **AC-M1** (020 AC-L1): after ≥2 chat turns, `memory_pages` gained rows with
  `source='chat'`, `page_type='conversation'`, `user_id` = the Clerk id,
  `tags @> ARRAY['chat']`, and `metadata_->>'session_id'` populated — checked
  alongside the existing `user_insights` growth check.
- **AC-M2** (020 AC-L2): start a NEW session and ask about the prior session's
  topic → the answer reflects recall (with debug access: the assembled prompt
  contains exactly one `<memories>` block).
- **AC-M3** (020 AC-L3): perceived chat latency unchanged (recall adds 1-2 DB
  queries + an access-counter update per turn).

## How to run

Fold into the next release smoke on the deployed env (workflows/release.md), or a
one-off manual session against the EC2 deployment: one resumed session covering
all three checks, transcript recorded in `reports/`. Success metric from 017:
0 re-answered questions across a 5-session resumed-chat smoke; `tokens_used` per
resumed turn lower than pre-017 baseline.
