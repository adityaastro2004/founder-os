---
id: 005
title: Agent Evolution — temporal memory injection into prompts
status: done
stage: done
owner: eng-product
created: 2026-06-10
dependencies: []
links: [docs/agent-evolution.md, docs/decisions.md]
---

# 005 — Temporal memory injection

> **Closed 2026-07-19 — subsumed by [task 020](020-chat-semantic-memory.md)** (ADR-014): `<memories>` recall injection shipped in `BaseAgent._render_memories_context`, reusing run()'s query embedding; chat capture (the write side 005 assumed existed) shipped with it.

## Objective
The temporal knowledge graph (`memory_pages`/`memory_links`, composite-scored recall)
is a standalone REST API today and is NOT injected into agent prompts. Wire it in so
agents recall relevant founder history automatically.

## Scope sketch (design: docs/agent-evolution.md §2)
- Inject top composite-scored `memory_pages` into `AgentMemory.build_context`.
- Define a ProfileIntelligence synthesis cadence (every N interactions).

## Acceptance criteria (to refine at Analyze)
- [ ] Relevant memory pages appear in an agent's built context (test).
- [ ] Bounded injection size; respects per-user scoping.

> Reuse: `app/memory/manager.py`, `app/agents/memory.py:build_context`,
> `app/agents/base.py:395`. Low-risk, high-leverage — sequence with 003.
