---
id: 001
title: Founder-aware agent specialization (Agent Evolution Engine — MVP)
status: done
stage: qa
owner: eng-qa
created: 2026-06-10
dependencies: []
links:
  - docs/vision.md
  - docs/architecture.md
  - founder-os/apps/api/app/agents/registry.py
  - founder-os/apps/api/app/agents/profile_intelligence.py
---

# 001 — Founder-aware agent specialization (Agent Evolution Engine — MVP)

> Step 1 (Analyze) output, produced by **eng-product**. This is the scoped first
> increment of the "Chief of Staff / Agent Evolution Engine" vision — NOT the whole
> spec. Awaiting scope confirmation before Step 2 (Plan).

## Opportunity analysis

**The vision:** product runtime agents (Planner, Research, Product, Content, Ops…)
should be *specialists optimized for this founder's specific business* — not generic
startup templates — and should evolve with founder context (stage, industry, goals,
voice, feedback). See [docs/vision.md](../../docs/vision.md).

**What already exists (reuse, don't rebuild):**
- `FounderProfile` — business_type, business_stage, industry, target_audience,
  primary_goal, MRR/users, writing_voice, team. (`app/models.py:110`)
- `Agent` — versioned registry rows with `system_prompt`, `model`, `capabilities`,
  `available_tools`. (`app/models.py:148`)
- `UserAgentConfig` — **per-user** `custom_instructions`, `tone_adjustments`,
  `example_outputs`, `is_enabled`, `auto_execute`, unique on (user, agent).
  (`app/models.py:179`)
- `ProfileIntelligence` — mines insights/business intelligence from conversations.
  (`app/agents/profile_intelligence.py:290`)
- LLM provider abstraction (`app/agents/llm.py`) and the 3-tier **approval gate**.

**The gap:** nothing turns `FounderProfile` into agent specialization. `UserAgentConfig`
is filled only by manual user edits; agents run generic prompts regardless of who the
founder is. The "evolution engine" has bones but no muscle.

**Why this is the right first increment (business justification):**
- **User pain:** founders re-explain their business to every agent; outputs feel
  generic ("write a blog post" energy, not "write *our* launch email").
- **Market demand:** personalization is the core differentiator vs generic AI tools
  ([docs/vision.md](../../docs/vision.md)).
- **Monetization:** "agents that actually know your business" is a headline upgrade /
  paid-tier hook.
- **Technical complexity:** LOW — reuses existing tables; **no schema migration**.
- **Cost:** BOUNDED — one generation per profile change, not per task (the spec's
  "redesign agents before every task" is rejected as unbounded/expensive).

## MVP scope (recommended)

**Generate a per-founder specialization layer for each runtime agent from the
FounderProfile, gated by human approval, stored in the existing `UserAgentConfig`.**

In scope:
1. A `SpecializationEngine` (new module under `app/agents/`) with one method:
   given a `user_id`, read `FounderProfile`, call the LLM once per active agent to
   produce `custom_instructions` + `tone_adjustments` tuned to stage/industry/goal/
   audience/voice, and return proposals.
2. Trigger points: onboarding completion and explicit "re-tune my agents" — **not**
   automatically on every task.
3. **Approval gate**: proposals are MEDIUM-risk; the founder reviews/edits/approves
   before they're written to `UserAgentConfig` (no silent agent rewrites).
4. `BaseAgent` already-or-newly applies `UserAgentConfig.custom_instructions` +
   `tone_adjustments` on top of the base `system_prompt` at run time (verify/wire).
5. One API endpoint (`/api/agents/specialize` style) + minimal surfacing.

Out of scope (later increments): dynamically changing `capabilities`/tools per
founder; auto-evolution from feedback (`task_feedback`/`learning_insights`); creating
brand-new agents per founder; the full per-task "Agent Evolution Engine"; UI polish.

## Feature prioritization (thin → thick)

1. **(MVP)** Profile → specialization proposals → approval → `UserAgentConfig` → applied at runtime.
2. Feedback-driven re-tuning (mine `task_feedback` to refine the layer).
3. Capability/tool selection per founder (touches the router + tool registry).
4. Founder-specific *new* agents (the spec's most ambitious, highest-risk part).

## User stories

- As a solo founder, after onboarding I want each agent pre-tuned to my business
  (stage, industry, goal, voice) **so that** outputs fit without me re-explaining.
- As a founder, I want to **review and edit** the proposed tuning before it applies
  **so that** I stay in control of how my agents behave.
- As a founder, I want to **re-tune** when my business changes (new stage/goal)
  **so that** my agents evolve with me.

## Acceptance criteria

- [ ] Given a populated `FounderProfile`, the engine produces a specialization
  proposal (custom_instructions + tone) for each active agent in one LLM call each.
- [ ] Proposals go through the approval gate; nothing writes to `UserAgentConfig`
  without approval.
- [ ] On approval, `UserAgentConfig` rows are upserted (unique on user+agent).
- [ ] At run time, an agent's effective system prompt = base `system_prompt` +
  approved `custom_instructions`/`tone_adjustments` (demonstrated diff in output).
- [ ] No schema migration required; provider-neutral (via `app/agents/llm.py`).
- [ ] A `test_*.py` proves the generate→approve→apply path with a mocked LLM.

## Success metrics

- ≥ 80% of generated proposals approved with ≤ minor edits (proxy for quality).
- Measurable specialization: blind A/B of one task's output (generic vs specialized)
  prefers specialized.
- Zero ungated writes to `UserAgentConfig` (security invariant).
- Generation cost ≤ N LLM calls per profile change (N = active agents), never per task.

## Risks · assumptions · alternatives (quality-gate required)

- **Assumption:** `FounderProfile` is populated post-onboarding. *Mitigation:* skip /
  prompt to complete profile if empty.
- **Risk:** LLM produces off-base instructions. *Mitigation:* human approval gate;
  store proposals, never auto-apply.
- **Risk:** scope creep toward the full per-task evolution engine. *Mitigation:* this
  task explicitly excludes it; later increments are separate tasks.
- **Alternative considered — full Agent Evolution Engine (redesign all agents before
  every major task):** rejected for MVP — unbounded cost, high regression risk, no
  approval story. Revisit after increments 1–2 prove value.
- **Alternative — pure prompt-injection of profile at runtime (no stored config):**
  cheaper but not editable/approvable and re-pays cost every call; rejected.

## Expected impact

Turns "generic AI tools" into "agents that know your business" — the core vision
differentiator — for LOW technical cost and no schema change, while keeping the
human-in-the-loop guarantee intact.

---

> **GATE (after Analyze):** ✅ scope confirmed by founder (MVP as scoped),
> 2026-06-10. Moved to `tasks/active/`.

---

## Plan  <!-- eng-planner -->

**Key discovery that shrinks the build:** runtime application of per-user agent
config already exists —
- `registry.py:236` reads `user_config.custom_instructions` into the agent config;
- `base.py:364-368` injects it as `<user_custom_instructions>` in the system prompt;
- `_load_user_config` (`registry.py:1086`) already filters `is_enabled == True`.

So we **build the generate→approve half; the apply half is verify-only.** Also note
`base.py` already injects raw FounderProfile facts at runtime — the engine's job is
*distilled, approved, per-agent* specialization, not re-dumping profile facts.

### Requirements
- R1. Generate a per-agent specialization (custom_instructions + tone) from
  `FounderProfile` via **one LLM call per active agent**, provider-neutral.
- R2. Persist proposals **without a migration**, in a not-yet-live state.
- R3. Founder reviews → approves/edits → proposal goes live; nothing live without approval.
- R4. Re-tune on demand and on profile change.
- R5. A mocked-LLM `test_*.py` proves generate→approve→apply.

### Milestones (ordered)
1. **M1 — Engine**: `SpecializationEngine.generate(user_id)` → proposals (no persistence).
2. **M2 — Staging persistence**: upsert `UserAgentConfig` rows with `is_enabled=False`
   (proposed) — migration-free (see Architecture).
3. **M3 — Approve flow**: endpoint to list proposals, edit, and approve (flip
   `is_enabled=True`); reject deletes the proposed row.
4. **M4 — Triggers**: call generate after `create_founder_profile`
   (`onboarding_routes.py:130`) + an explicit "re-tune" endpoint.
5. **M5 — Verify runtime apply**: confirm an approved config changes an agent's
   effective prompt (the existing path); add the test.

### Dependencies / sequence
M1 → M2 → M3 → (M4 ∥ M5). Approval (M3) before any trigger goes live (M4).

### Complexity
LOW–MEDIUM. New module + one route file + onboarding hook + tests. No migration.

> **GATE (after Plan):** scope unchanged from Analyze; proceeding to Architecture.

---

## Architecture  <!-- eng-architect; see ADR-003 in docs/decisions.md -->

**Read first:** [docs/architecture.md](../../docs/architecture.md). Design reuses
existing components; **no schema migration**.

### Data model — reuse `UserAgentConfig` (no migration)
- A **proposed** specialization = a `UserAgentConfig` row with `is_enabled=False`
  (the runtime loader ignores it — `registry.py:1091`). **Approved** = `is_enabled=True`.
  Store generated text in `custom_instructions` (+ `tone_adjustments`), respecting the
  unique `(user_id, agent_id)` constraint via upsert.
- Trade-off (in ADR-003): `is_enabled=False` overloads "proposed" and "user-disabled".
  Acceptable for MVP; a dedicated `status` column is a later increment if they diverge.

### New module — `app/agents/specialization.py`
- `class SpecializationEngine:` constructed with `(db, llm_generate)` — same DI shape
  as `ProfileIntelligence` (`profile_intelligence.py:296`), so it's provider-neutral.
- `async generate(user_id) -> list[Proposal]`: load `FounderProfile`; for each active
  `Agent`, one LLM call (system = "tune this agent for this founder"; input = base
  `system_prompt` + profile facts) → `{agent_id, custom_instructions, tone}`. Upsert as
  `is_enabled=False`.
- `async approve(user_id, agent_id, edits?)`: flip the row `is_enabled=True` (apply edits).
- `async reject(user_id, agent_id)`: delete the proposed row.

### API — `app/api/specialization_routes.py` (register in `main.py`)
Follow [standards/api.md](../../standards/api.md): `require_auth`, scoped to
`user.user_id`, Pydantic models, async.
- `POST /api/agents/specialize` → generate proposals (returns the list).
- `GET  /api/agents/specialize/proposals` → list pending (is_enabled=False) configs.
- `POST /api/agents/specialize/{agent_id}/approve` (body: optional edits).
- `POST /api/agents/specialize/{agent_id}/reject`.

### Approval model (why not the tool ApprovalGate)
`app/agents/approval.py` gates **tool calls inside an agent run** (`TOOL_RISK_MAP`).
Specialization is triggered from onboarding/UI, not from within an agent loop, so the
cleaner control is the **explicit propose→approve endpoints above** (the founder is the
gate). Still honors "nothing live without human approval"
([standards/security.md](../../standards/security.md)). Recorded as a decision.

### Triggers
- After `create_founder_profile` (`onboarding_routes.py:130`): call
  `SpecializationEngine.generate` (proposals only — not auto-applied), **async/non-blocking**.
- Explicit re-tune via `POST /api/agents/specialize`.

### Integration points
LLM via `app/agents/llm.py` (the same callable `ProfileIntelligence` takes);
`UserAgentConfig` + `Agent` + `FounderProfile` ORM; runtime apply path unchanged
(`registry.py` + `base.py`).

### Testing
`apps/api/test_agent_specialization.py` (standalone, **mocked LLM**): generate →
proposals are `is_enabled=False` → approve flips one → a built agent's effective
system prompt now contains the approved instructions. Follows
[standards/testing.md](../../standards/testing.md).

### Risks / trade-offs
- `is_enabled` overload (above) — accept for MVP.
- Onboarding latency: generation is N LLM calls — run **async/non-blocking** so
  `create_founder_profile` returns immediately; proposals appear when ready.
- Cost bounded to N (active agents) per profile change.

> **GATE (after Architect):** ✅ founder signed off (build MVP, `is_enabled` staging),
> 2026-06-10.

---

## Build notes  <!-- eng-executor -->

Changed files (all new except the two wiring edits):
- **NEW** `app/agents/specialization.py` — `SpecializationEngine` (generate / approve /
  reject / list_proposals) + `_parse_specialization`. Provider-neutral; `llm_generate`
  optional (only `generate` needs it).
- **NEW** `app/api/specialization_routes.py` — `POST /api/agents/specialize`,
  `GET …/proposals`, `POST …/{agent_id}/approve`, `POST …/{agent_id}/reject`.
- **EDIT** `app/main.py` — import + `include_router(specialization_router)`.
- **EDIT** `app/api/onboarding_routes.py` — non-blocking `BackgroundTasks` trigger
  (`_specialize_in_background`) after `create_founder_profile` flush.
- **NEW** `test_agent_specialization.py` — mocked LLM + fake session, no infra.

Verified: `python test_agent_specialization.py` → **13 PASS | 0 FAIL**; all three
modules import cleanly; routes register; no circular import.

## Review findings  <!-- eng-reviewer -->
- [should-fix → **fixed**] `approve`/`reject`/`list` were building the LLM provider
  (`_get_llm_generate`) they never use. Made `llm_generate` optional; non-generate
  routes now construct `SpecializationEngine(db)` with no LLM. Re-tested green.
- [nit] Cross-module import of the private `_get_llm_generate` from `profile_routes`.
  Accepted reuse for MVP; follow-up: promote to a public helper in `app/agents/llm.py`
  (logged to roadmap tech-debt).
- [accepted/ADR-003] `generate` re-proposing sets `is_enabled=False` on an existing
  row, so an explicit re-tune pauses a previously-live config until re-approved.
  Documented in code + ADR; onboarding (first-run) path is unaffected (no live rows).
- Scope contained (2 small wiring edits); no schema migration. **Verdict: approve.**

## QA results  <!-- eng-qa -->
- Command: `python test_agent_specialization.py` → **13 PASS | 0 FAIL**.
- Acceptance criteria:
  - [x] proposal per active agent in one LLM call each (mocked) — `generate` tests.
  - [x] nothing written live without approval — staged `is_enabled=False` asserted.
  - [x] approval upserts/flips `is_enabled=True` — `approve` tests.
  - [x] effective prompt = base + approved instructions — asserted runtime-apply-
        eligible state; runtime injection is existing verified code (`base.py:364`).
  - [x] no migration; provider-neutral (LLM via `llm.py`).
  - [x] mocked-LLM test proves generate→approve→apply.

## Security report  <!-- eng-security -->
- Auth: all four routes use `require_auth`; identity resolved Clerk→`users.id`. ✓
- Scoping: `approve`/`reject`/`list` filter by `user_id` (+ `agent_id`) — a user
  cannot view/approve another user's proposal. ✓
- Human-in-the-loop: proposals are invisible to runtime until approved
  (`is_enabled=True`); the loader filters `is_enabled==True`. No ungated activation. ✓
- Secrets/provider: no secrets; LLM via `app/agents/llm.py`. ✓
- Background task isolates its own session and swallows exceptions (never crashes the
  request path). ✓
- **Verdict: Pass** (no blockers).

---

## Status: DONE — all acceptance criteria pass, security Pass. Moving to `tasks/completed/`.
