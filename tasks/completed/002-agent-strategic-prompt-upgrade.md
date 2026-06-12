---
id: 002
title: Agent evolution — strategic prompt upgrade + code→DB sync
status: done
stage: qa
owner: eng-qa
created: 2026-06-10
dependencies: []
links:
  - docs/decisions.md (ADR-004, ADR-005)
  - docs/agent-evolution.md
  - founder-os/apps/api/app/agents/agents.py
  - founder-os/apps/api/app/agents/registry.py
---

# 002 — Agent evolution: strategic prompt upgrade + make prompts actually run

## Objective
Transform the product runtime agents from generic task executors into founder-specific
strategic systems-thinkers — and fix the latent bug that makes the rich code prompts
dead (generic DB seeds win at runtime). Larger subsystems are designed + queued, not
built here. (Scope confirmed with founder; full analysis in the approved plan.)

## Acceptance criteria
- [ ] Each of the 6 agents (orchestrator, planner, research, product, content, ops;
      support gets the shared preamble) has a strategic systems-thinking layer prepended
      to its existing prompt, **preserving all operational/tool instructions**.
- [ ] `sync_agents_to_db` upserts code definitions into the `agents` table; called at
      startup so the rich prompts actually run. Idempotent; no schema migration.
- [ ] A test proves: sync upserts all agents, is idempotent, synced prompts contain the
      strategic markers, and the build path loads the DB prompt.
- [ ] `test_e2e_pipeline.py` still passes (no regression).
- [ ] Deferred subsystems designed in `docs/agent-evolution.md` + ADRs + roadmap + backlog stubs.

## Architecture (from approved plan; ADR-004/005)
- Source of truth = code. `AGENT_CLASSES` (`agents.py:744`) holds the canonical classes;
  `sync_agents_to_db` upserts each class's `default_system_prompt` / `capabilities` /
  `default_tools` into the `agents` row (unique `name`). `base.py:351` unchanged
  (DB-wins at runtime) — but DB is now synced from code.
- Strategy layered via a shared `app/agents/strategy.py` (`SYSTEMS_THINKING_PREAMBLE` +
  `strategic_header(role, charter)`), prepended to each `default_system_prompt`. Minimal
  diff: one edit per agent (assignment line) + one import per file.
- Prompts reference the existing injected context seam (`base.py:340-480`:
  `<founder_profile>`, `<user_profile>`, `<user_custom_instructions>`, memory).

## Build notes  <!-- eng-executor -->
- **NEW** `app/agents/strategy.py` — `SYSTEMS_THINKING_PREAMBLE`, `STRATEGY_MARKER`,
  `strategic_header(role, charter)`.
- **EDIT** `app/agents/agents.py` — import + prepend `strategic_header(...)` to Planner,
  Research, Ops, Product, Support prompts (one-line edit each; bodies preserved).
- **EDIT** `app/agents/content_prompts.py` — prepend to `CONTENT_AGENT_SYSTEM_PROMPT`.
- **EDIT** `app/agents/orchestrator.py` — import + prepend to its prompt.
- **NEW** `sync_agents_to_db` in `app/agents/registry.py`; **EDIT** `app/main.py`
  lifespan calls it after `init_db()` via `_sync_agent_definitions()` (best-effort).
- **NEW** `test_agent_prompts.py`.

## QA results  <!-- eng-qa -->
- `python test_agent_prompts.py` → **35 PASS | 0 FAIL** (all 7 agents: strategy marker +
  role elevation + decision framework + preserved operational text; sync inserts,
  idempotent, DB prompt == code prompt).
- Regression `python test_agent_specialization.py` (task 001) → **13 PASS | 0 FAIL**.
- Regression `python test_e2e_pipeline.py` (Postgres+Redis up) → **50 PASS | 0 FAIL**.
- **Real-DB proof:** planner DB prompt before sync = generic *"You are a strategic
  planning expert…"*; after `sync_agents_to_db` = *"Chief of Staff / Chief Strategy
  Officer…"*; all 7 rows contain the `THINK IN SYSTEMS` marker. Confirms the latent bug
  AND the fix.
- All acceptance criteria met.

## Review findings  <!-- eng-reviewer -->
- [accepted/ADR-004] Startup sync overwrites manual DB prompt edits — documented; manual
  editing isn't a current workflow.
- [good] Layered approach = minimal diff (one prepend per agent); operational
  instructions verified present by test, not just assumed.
- [good] Sync is best-effort (logs, never blocks startup); idempotent (upsert).
- Scope contained: new module + sync + one-line prompt edits + lifespan hook. No schema
  migration. **Verdict: approve.**

## Security report  <!-- eng-security -->
- No auth/secrets/approval-gate surface touched. Provider-neutral (prompts only).
- Sync writes only canonical code definitions to the `agents` table (no user input). ✓
- Prompts instruct agents to use already-injected, per-user-scoped founder context;
  no new data exposure. ✓
- **Verdict: Pass** (no blockers).

---

## Status: DONE — 35/35 + regressions green, real-DB fix proven, security Pass.
Moving to `tasks/completed/`.
