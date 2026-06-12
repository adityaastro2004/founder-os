---
id: 003
title: Agent Evolution Engine — Founder Context Model + Agent Generator
status: done
stage: qa
owner: eng-qa
created: 2026-06-11
dependencies: [001, 002]
links: [docs/agent-evolution.md, docs/decisions.md]
---

# 003 — Agent Evolution Engine (Context Model + Generator)

## Objective
The leap from per-founder *overlay* (task 001) to per-founder *definition regeneration*:
build a Founder Context Model and an Agent Generator that regenerate each agent's full
definition (system prompt + decision framework + tool selection), versioned and
approval-gated, applied at runtime over the global agent. Closes Missing Piece #1
deeply, starts #2. (Approved plan = option A.)

## Acceptance criteria
- [ ] `FounderContextModelBuilder` distills FounderProfile + UserProfileIntel into a
      structured model; hashed for change detection; versioned upsert.
- [ ] `AgentGenerator` stages a full per-user definition per agent (status=proposed,
      version increments); never auto-activates.
- [ ] approve → active (supersedes prior active); reject → removed; rollback → prior version.
- [ ] Registry prefers the *active* per-user definition over the global Agent row.
- [ ] Approval-gated, versioned/reversible, bounded (N calls per context change),
      scoped to user_id, provider-neutral.
- [ ] Tests (mocked LLM) + real-DB proof + regressions green.

## Architecture (approved plan)
New tables `founder_context_models`, `agent_definitions` (ORM + schema.sql, no Alembic).
New `context_model.py`, `generator.py`, `evolution_routes.py`. Registry override in
`get()`. Onboarding trigger. Reuses task-001 pattern + `_get_llm_generate`, task-002
`strategy.py`/`AGENT_CLASSES`.

## Build notes  <!-- eng-executor -->
- **NEW tables** `founder_context_models`, `agent_definitions` — ORM in `app/models.py`
  + DDL in `schema.sql` (no Alembic, per repo practice); created in dev via
  `Base.metadata.create_all` for the two tables.
- **NEW** `app/agents/context_model.py` — `FounderContextModelBuilder` (distill +
  hash + versioned upsert).
- **NEW** `app/agents/generator.py` — `AgentGenerator` (generate/approve/reject/
  rollback; tool selection intersected with the real menu; never auto-activates).
- **EDIT** `app/agents/registry.py` — `_load_active_definition` + `get()` prefers the
  active per-user definition's prompt + tools over the global agent row.
- **NEW** `app/api/evolution_routes.py` (evolve / context-model / proposals /
  approve / reject / rollback) + **EDIT** `app/main.py` (register).
- **EDIT** `app/api/onboarding_routes.py` — onboarding background trigger now runs the
  evolution engine (supersedes task-001's overlay trigger; specialize endpoints remain).
- **NEW** `test_agent_evolution.py`.

## QA results  <!-- eng-qa -->
- `python test_agent_evolution.py` → **22 PASS | 0 FAIL** (context distill+hash+change
  detection, generator staging/versioning, approve→active+supersede, reject, rollback,
  registry-override contract).
- **Real-DB proof:** seeded a test founder → generate → approve planner → `registry.get
  ('planner', user)` returned an agent whose effective `system_prompt` is the
  PER-FOUNDER regenerated definition (not the global task-002 prompt). End-to-end fix
  confirmed; test founder cleaned up.
- Regressions green: `test_agent_prompts` 35/35, `test_agent_specialization` 13/13,
  `test_e2e_pipeline` 50/50.
- All acceptance criteria met.

## Review findings  <!-- eng-reviewer -->
- [good] `selected_tools` intersected with the real `default_tools` menu — the LLM can't
  invent tools; falls back to the full menu if it strips everything.
- [good] LLM only required for `generate`; approve/reject/rollback/list construct the
  engine without it. Per-user queries scoped by `user_id`(+`agent_name`).
- [accepted/ADR-006] Onboarding trigger switched from task-001 overlay → evolution; the
  specialize endpoints remain for manual tweaks (documented).
- [accepted/ADR-006] `is_*`/full-regeneration is sensitive → hard approval gate; never
  auto-activates; versioned + reversible. **Verdict: approve.**

## Security report  <!-- eng-security -->
- All routes `require_auth`, identity resolved Clerk→`users.id`; every query scoped to
  the founder. A founder cannot view/approve another founder's definitions. ✓
- Human-in-the-loop preserved: proposals are `proposed` and invisible to runtime until
  `active`; the registry only serves `status='active'` rows. No ungated activation. ✓
- No secrets; provider-neutral (LLM via `llm.py`); background task isolates its own
  session and swallows exceptions. ✓
- **Verdict: Pass** (no blockers).

---

## Status: DONE — 22/22 + regressions green, real-DB per-founder regeneration proven,
security Pass. Moving to `tasks/completed/`.
