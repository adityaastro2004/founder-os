---
id: 018
title: Scope event-bus SSE streams per user/session
status: backlog
stage: product
owner: eng-product
created: 2026-07-18
dependencies: []
links: [docs/architecture.md, founder-os/apps/api/app/agents/event_bus.py]
---

# 018 — Scope event-bus SSE streams per user/session

## Objective

`POST /api/agents/orchestrate/stream` relays progress by psubscribing to the
global Redis patterns `fos:events:tool.*` / `agent.*` / `delegation.*` /
`orchestration.*`. `Event` (`app/agents/event_bus.py`) carries no
`user_id`/`session_id`, so with two concurrent users each SSE stream shows the
other user's tool calls and delegation previews (`task_preview`,
`result_preview`). Found during the background-chat work (2026-07-18); left out
of that change because fixing it means touching every event publisher.

## Acceptance criteria

- [ ] `Event` carries the originating `user_id` (and ideally `session_id`);
      publishers in `execution.py` / `orchestrator.py` / delegation paths fill it.
- [ ] `orchestrate_stream` only forwards events matching the requesting user
      (channel-per-user, e.g. `fos:events:{user_id}:…`, or filter on the field).
- [ ] `/api/activity/stream` gets the same scoping review.
- [ ] Two concurrent sessions with different users verified isolated.

## Out of scope

- Replacing the event bus itself.
