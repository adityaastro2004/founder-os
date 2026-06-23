---
id: 004
title: n8n-backed auto-workflow system (invisible execution + visualization backend)
status: backlog
stage: planner
owner: eng-planner
created: 2026-06-18
dependencies: []
links: [tasks/backlog/004-workflow-execution-engine.md, docs/agent-evolution.md, docs/roadmap.md, docs/decisions.md]
---

# 004 — n8n-backed Auto-Workflow System

> **Supersedes** the earlier sketch in `tasks/backlog/004-workflow-execution-engine.md`
> (homegrown engine parsing `steps` JSONB). The founder has decided to use **n8n as an
> invisible, AI-driven execution + visualization backend** rather than building a bespoke
> engine. Keep that file only as historical context; this spec is the active definition of
> what to build. Architecture (the *how* — compiler, REST push, callback contract) is for
> `eng-planner` / `eng-architect`, not this doc.

## Objective
Make the readme's headline promise real: a founder describes a goal in plain language, the
**Orchestrator auto-generates a workflow**, and that workflow is **compiled and pushed to a
self-hosted n8n instance** which executes it (cron/webhook triggers, HTTP nodes that call
back into Founder OS agents) and renders it in n8n's free visual editor so the founder can
**view and edit** any generated flow. The founder never wires a flow by hand; n8n is
invisible infrastructure. Real-world actions remain gated by the existing 3-tier approval
gate. This turns the unused `workflow*` tables into a live, founder-supervised system.

## Why this matters (problem & goal)
The vision's single biggest differentiator is **auto-generated workflows** — "if you have
to design an automation by hand, the tool has already failed" (readme Philosophy). Today
that promise is unfulfilled: the `WorkflowTemplate` / `Workflow` / `WorkflowExecution` /
`Task` tables exist (`founder-os/apps/api/app/models.py:205-369`) but are **unused stubs** —
no router, no generator, no execution engine, no scheduler wiring. A solo founder currently
gets one-shot orchestrations but **nothing recurring, durable, inspectable, or editable**.

This solves three concrete pains for a solo founder:
1. **Recurrence without busywork** — "every Monday, prep my ops standup + metrics check"
   should run itself, not require a re-prompt each week.
2. **Trust through visibility** — a founder won't hand real actions to a black box. n8n's
   visual editor lets them *see* exactly what the AI built and *tweak* it without code.
3. **No vendor lock-in / no cost** — self-hosted n8n (OSS) matches the OSS-first,
   local-first principle (Ollama default, Postgres + Redis, no paid API required).

Strategic fit: n8n is **invisible infrastructure**, not a new top-level surface. The
Orchestrator stays the single entry point (vision: "one entry point, zero routing"); n8n is
where generated flows live, run, and become editable.

## User stories  <!-- eng-product -->

**US-1 — Auto-generate a workflow from a natural-language goal**
As a founder, I want to describe a recurring outcome in plain language (e.g. "every Monday
morning, pull last week's metrics, draft a team update, and flag anything off-track") so
that the Orchestrator generates a complete, runnable workflow without me wiring any steps.

**US-2 — View and edit a generated workflow visually**
As a founder, I want to open any generated workflow in a visual editor and see its trigger,
steps, and agent calls — and tweak them — so that I can trust, correct, and refine what the
AI built without writing code or re-prompting from scratch.

**US-3 — Schedule and trigger workflows**
As a founder, I want a workflow to run on a schedule (cron) or fire on an event/webhook so
that recurring work happens automatically and time-sensitive work triggers itself, without
me remembering to ask.

**US-4 — Real-world actions go through the approval gate**
As a founder, I want any workflow step that takes an irreversible or externally-visible
action (send email, post to social, deploy, make a payment) to pause for my explicit
approval so that the system can act on my behalf without ever acting *without* my consent.

**US-5 — See workflow run history and results**
As a founder, I want to see each run of a workflow — when it ran, what triggered it,
pass/fail, what it produced, and any errors — so that I know my AI team is working and can
diagnose anything that went wrong.

## Acceptance criteria

**US-1 — Auto-generate**
- [ ] Given a free-text goal sent to the existing orchestrate entry point, the system
      produces a persisted `Workflow` row (`name`, `description`, `steps` JSONB populated)
      owned by the requesting user — no manual step authoring.
- [ ] The generated `steps` represent a coherent ordered plan (trigger + ≥1 agent/action
      step); each step names the responsible specialist agent or action.
- [ ] The same `Workflow` is compiled and pushed to the self-hosted n8n instance via n8n's
      REST API, and the response records the n8n workflow identifier against the Founder OS
      `Workflow` row.
- [ ] If generation or push fails, the founder gets an actionable error (not a silent
      failure or raw stack trace), per `standards/ux.md`.

**US-2 — View / edit**
- [ ] For any generated workflow, the founder can reach its n8n visual editor view (e.g. a
      link/embed from the dashboard) and see the trigger, steps, and agent/HTTP nodes.
- [ ] An edit made in n8n (e.g. changing the cron, reordering or removing a step) is
      reflected on the next run — the n8n-side definition is authoritative for execution.
- [ ] Founder OS surfaces *which* workflows exist and their status without the founder
      needing to know n8n is involved (n8n is invisible by default; the editor is the
      "advanced" affordance).

**US-3 — Schedule / trigger**
- [ ] A workflow can be set to run on a cron schedule; `is_scheduled`, `schedule_cron`, and
      `next_run_at` on the `Workflow` row reflect the schedule, and n8n fires the run at the
      scheduled time.
- [ ] A workflow can be triggered on demand (founder-initiated "run now") and the run
      executes via n8n.
- [ ] A webhook/event trigger causes the corresponding workflow to execute (at least one
      working event-trigger path demonstrated).
- [ ] `last_run_at`, `total_runs`, and `successful_runs` on the `Workflow` row update after
      each run.

**US-4 — Approval gate (non-negotiable)**
- [ ] When a workflow step invokes a HIGH-risk tool (see `app/agents/approval.py`
      `HIGH_RISK_TOOLS` — send_email, post_to_social_media, deploy, make_payment, etc.), the
      run pauses and a pending approval is created via the existing `ApprovalGate`; the
      action does **not** execute until the founder approves.
- [ ] HIGH-risk steps cannot be bypassed or downgraded by workflow config or by an n8n-side
      edit — the gate is enforced **server-side in Founder OS**, not in n8n. (n8n editing
      must not become an approval-gate escape hatch.)
- [ ] A rejected approval halts the affected step and is recorded on the run (status +
      reason); the run does not silently proceed as if approved.
- [ ] LOW/MEDIUM steps follow existing per-user approval preferences (unchanged behavior).

**US-5 — Run history / results**
- [ ] Each run creates a `WorkflowExecution` row with `status`, `trigger_type`,
      `started_at`/`completed_at`, `duration_seconds`, `steps_completed`/`steps_failed`,
      and `output_summary` (and `error_message` on failure).
- [ ] The founder can list a workflow's run history and open a single run to see its
      result/summary and any error — via an authenticated Founder OS endpoint (Clerk JWT,
      `require_auth`); a user only sees their own workflows and runs.
- [ ] A failed run is clearly distinguishable from a successful one and surfaces a
      human-readable reason.

**Cross-cutting**
- [ ] All new Founder OS endpoints require a valid Clerk JWT and scope data to the
      authenticated user (`standards/security.md`).
- [ ] The system runs against a **self-hosted n8n** with no paid dependency; n8n connection
      config is environment-driven and secret-safe (no tokens logged/committed).
- [ ] Schema changes (if any beyond the existing tables) go through Alembic, not hand-edited
      `schema.sql`.
- [ ] Manual verification is recorded end-to-end for the v1 slice (see below).

## Success metrics  <!-- eng-product -->
- **Loop proven:** ≥1 founder goal → generated workflow → pushed to n8n → executed → result
  visible in Founder OS, with an approval gate honored on a HIGH-risk step. (Binary gate for
  "v1 done.")
- **Generation reliability:** ≥70% of generated workflows run end-to-end **without manual
  fixes** in the n8n editor (measured over the first batch of dogfood workflows). Target
  rising to ≥85% as generation matures.
- **Time-to-first-workflow:** founder goes from typing a goal to a scheduled, running
  workflow in **under 2 minutes**, zero manual node wiring.
- **Approval integrity:** **100%** of HIGH-risk steps create an approval before acting —
  zero un-gated external/irreversible actions (hard safety metric; any miss is a P0).
- **Edit adoption (trust signal):** of generated workflows, the share the founder *views*
  in the editor (visibility working) and the share they *edit* (a healthy small number means
  generation is good but trust-via-tweak is available). Track, don't over-optimize.
- **Recurrence value:** number of workflows running on a schedule and their successful-run
  rate (`successful_runs / total_runs`) trending up over time.

## Out of scope (v1 — be explicit)
- **User-built-from-scratch flows inside Founder OS.** No drag-and-drop builder in our UI;
  authoring is always Orchestrator-generated. (Editing an *already-generated* flow in n8n is
  in scope; authoring a brand-new flow by hand is not.)
- **A marketplace / library of shareable workflow templates.** `WorkflowTemplate` may be
  used internally as a generation artifact, but a public/community template marketplace is a
  later-phase idea.
- **Automatic workflow *evolution*** (workflows that self-rewrite as metrics/integrations
  change). That is the readme's "workflows evolve automatically" promise and a follow-on
  phase — v1 generates and runs; it does not auto-mutate existing flows.
- **Managed/cloud n8n or a hosted n8n offering.** Self-hosted OSS only for v1.
- **Branching/conditional/loop-heavy workflow logic.** v1 targets linear (and simple
  scheduled) flows; complex control flow comes later.
- **Multi-user/team-shared workflows.** Per-user ownership only, consistent with current
  auth model.
- **Replacing tool stubs** (`web_search`, `get_business_metrics`). Out of scope here; if a
  generated workflow depends on a stub, that's flagged as a known gap, not fixed in this task.

## Roadmap priority & phasing

**Priority:** Promote from **Later → Next (committed)**, and frame as the flagship "make the
differentiator real" effort. Rationale: auto-generated workflows are the product's headline
claim and currently the largest gap between pitch and reality. The Agent-Evolution items
(feedback loop, temporal memory injection) sharpen *agent quality*; this delivers a
*net-new capability* the whole pitch rests on. It is bigger/riskier than those, so it ships
as a thin vertical slice first and earns its later phases.

### v1 — Thin vertical slice (prove the loop end-to-end)
Goal: **one founder goal → Orchestrator generates → pushed to self-hosted n8n → runs →
result visible in Founder OS, with the approval gate respected.**
- A single generated workflow with a simple **linear** step plan.
- One **trigger type** working end-to-end: a **manual "run now"** plus a **cron schedule**
  (reuse the scheduling fields already on `Workflow`).
- Compiled + pushed to self-hosted n8n via REST; n8n executes and calls back into a Founder
  OS agent via an HTTP node.
- At least **one HIGH-risk step** demonstrably routed through `ApprovalGate` (gate enforced
  server-side in Founder OS, not n8n), with both an approve and a reject path verified.
- `WorkflowExecution` rows written; a Founder OS endpoint lists runs and shows one run's
  result/error. Authenticated, user-scoped.
- Minimal dashboard affordance: list workflows, "run now", view run history, and a link out
  to the n8n editor (US-2 visibility). Full polish deferred.

Done-when: the success metric "Loop proven" is satisfied with recorded manual verification.

### v2 — Make it trustworthy and routine
- Event/webhook triggers as a first-class path; richer trigger config.
- Tighter view/edit experience (clear surfacing of edits round-tripping; better mapping
  between Founder OS `Workflow` and the n8n definition).
- Run observability: per-step status, partial-progress streaming to the dashboard
  (reuse `useEventSource`), better error messaging.
- Reuse of `WorkflowTemplate` as a generation/caching artifact so common patterns regenerate
  faster.

### v3 — Evolution & breadth (later)
- Workflow **auto-evolution** — flows update themselves as metrics/integrations/feedback
  change (ties into the Agent-Evolution feedback loop, tasks 003-followup / 007).
- Conditional/branching/loop logic in generated flows.
- (Idea) template marketplace; team-shared workflows.

## Requirements / open questions  <!-- eng-planner / needs founder sign-off -->
These are product-level unknowns I could not resolve from the repo or the stated decision —
flag for `eng-planner` / founder before architecture:

1. **`steps` JSONB schema (the IR).** What is the canonical intermediate representation the
   Orchestrator emits and the compiler translates to n8n nodes? This is the load-bearing
   contract for the whole system. *Architecture decides the shape; product needs it to be
   expressive enough for: trigger + ordered agent-call steps + an action step that maps to a
   risk-classified tool.* Recommend an ADR.
2. **Callback security.** n8n HTTP nodes call back into Founder OS agents — these callbacks
   bypass the interactive Clerk-JWT user session. How are they authenticated and scoped to
   the owning user without weakening the security model? (Service token? signed
   per-workflow secret?) **This is the highest-risk open item and must involve eng-security.**
2b. **Where the approval gate sits in the round-trip.** Confirmed product requirement: the
    gate is enforced in Founder OS, never in n8n. Open: when n8n calls back to run a
    HIGH-risk step and the action is pending approval, does the run *pause and resume* (n8n
    waits / is re-triggered on approval) or does the Founder OS callback *block*? Needs an
    architecture call; product constraint is only that the action cannot fire un-approved.
3. **n8n deployment in the dev/start path.** Should self-hosted n8n be added to
   `docker-compose.yml` / `start.sh` so the local-first stack includes it by default, or is
   it an opt-in service? (Affects "runs on a laptop with zero cost" promise.)
4. **Editor surfacing.** For v1, is a link-out to the n8n UI acceptable (founder logs into
   n8n), or is an embedded/SSO-style view required to keep n8n "invisible"? Product leans
   link-out for v1; confirm acceptable.
5. **Conflict resolution on edits.** If the founder edits a flow in n8n and later the
   Orchestrator regenerates/updates it, who wins? v1 sidesteps this (no auto-regen), but the
   product rule for v2+ should be decided (suggest: founder edits are sticky / never silently
   overwritten).
6. **Relationship to the existing one-shot orchestration path.** A "workflow" (durable,
   scheduled, in n8n) vs a one-shot `/orchestrate` call — is every orchestration a candidate
   to be "saved as a workflow", or only when the founder asks for something recurring? Product
   default: only persist as a workflow when recurrence/scheduling/reuse is intended; otherwise
   it stays a one-shot run.

---

## Plan  <!-- eng-planner; appended below the product spec — do not overwrite above -->

> Planning only. Turns the approved product spec (US-1..US-5, acceptance criteria,
> v1 slice) into requirements, milestones, sequenced tasks, the critical path, risks,
> and the ADR-worthy items that must be resolved by `eng-architect` **before** any code
> is written. No architecture decisions are made here — design questions are flagged and
> handed off. Scope is the **v1 thin vertical slice** unless explicitly noted v2/v3.

### Grounding (what already exists — to reuse, not rebuild)
- **DB tables exist and are unused stubs:** `Workflow`, `WorkflowExecution`,
  `WorkflowTemplate`, `Task`, `TaskDependency` (`app/models.py:205-371`). They already
  carry the fields the spec needs (`steps` JSONB, `is_scheduled`/`schedule_cron`/
  `next_run_at`/`last_run_at`, `total_runs`/`successful_runs`, exec `status`/`trigger_type`/
  `started_at`/`completed_at`/`duration_seconds`/`steps_completed`/`steps_failed`/
  `output_summary`/`error_message`). There is **no Alembic migration** creating them yet.
  **No new columns are presumed needed for v1** beyond an n8n workflow-identifier reference
  on `Workflow` (see open question O-1 / Task DB-1).
- **Approval gate exists and is solid:** `app/agents/approval.py` — `ApprovalGate.check()`
  already forces HIGH-risk tools to a pending approval with **no bypass**, refuses
  `always_allow` on HIGH-risk, and `approve()`/`reject()` resolve via Redis. Approval REST
  surface already exists: `app/api/approval_routes.py` (`/api/approvals/pending`,
  `/{id}/approve`, `/{id}/reject`). **Reuse this; do not reimplement.**
  - **Load-bearing constraint discovered:** the gate is **non-blocking / re-run based** —
    `check()` returns a decision; if pending, the caller is expected to stop and the action
    runs on a later re-run/execute. There is currently **no "wait until resolved then
    continue"** primitive. The n8n round-trip needs exactly that (pause/resume or poll).
    This is why open question O-3 (where the gate sits in the round-trip) is on the
    critical path — see RISK-2.
- **Router registration pattern:** add `app/api/<name>_routes.py`, import + `include_router`
  in `app/main.py` (~lines 8-24 imports, 85-101 registration).
- **Background execution exists:** Celery (`app.celery_app`, queues
  `default,agents,orchestrator`) and APScheduler (`app/scheduler.py`, weekly planner). The
  decision context says **n8n owns triggering (cron/webhook)** — so v1 does NOT add
  Founder-OS-side cron for workflows; APScheduler stays for the weekly planner only. Flag
  for architect: confirm n8n is the single scheduler of record (O-4) to avoid double-firing.
- **Orchestrator** (`app/agents/orchestrator.py`) is the single entry point; it already
  decomposes → plans (ordered, parallel-aware) → delegates. Workflow generation extends
  this path; it does not create a second entry point.

### 1. Requirements

#### Functional (FR)
- **FR-1 (US-1, generation):** A free-text goal sent through the existing orchestrate entry
  point produces a persisted `Workflow` row owned by the requesting user, with `name`,
  `description`, and a populated `steps` JSONB (the IR) representing trigger + ≥1 ordered
  agent/action step; each step names its responsible specialist agent or action. No manual
  step authoring.
- **FR-2 (US-1, compile+push):** The same `Workflow` is compiled from the IR to n8n
  workflow JSON and pushed to self-hosted n8n via n8n's REST API; the returned n8n workflow
  identifier is recorded against the Founder OS `Workflow` row.
- **FR-3 (US-1, errors):** Generation or push failure yields an actionable, user-readable
  error (no silent failure, no raw stack trace) per `standards/ux.md`.
- **FR-4 (US-3, triggers):** A workflow runs (a) on demand via a Founder-OS "run now"
  endpoint and (b) on a cron schedule reflected in `is_scheduled`/`schedule_cron`/
  `next_run_at`, with n8n firing the scheduled run. (Event/webhook trigger is **v2** per the
  spec; v1 demonstrates manual + cron only.)
- **FR-5 (US-4/US-5, callback):** n8n executes the flow and, per step, calls back into a
  Founder OS agent over an authenticated HTTP callback that runs the named agent/action for
  the owning user and returns the step result to n8n.
- **FR-6 (US-4, approval gate):** When a callback step invokes a HIGH-risk tool, the run
  pauses and a pending approval is created via the **existing** `ApprovalGate`; the action
  does not execute until the founder approves. A **reject** halts the step and is recorded
  on the run (status + reason); the run does not proceed as if approved. LOW/MEDIUM steps
  keep existing per-user preference behavior. The gate is enforced **server-side in Founder
  OS** and is not bypassable by an n8n-side edit.
- **FR-7 (US-5, run records):** Each run creates/updates a `WorkflowExecution` row with
  `status`, `trigger_type`, `started_at`/`completed_at`, `duration_seconds`,
  `steps_completed`/`steps_failed`, `output_summary` (and `error_message` on failure);
  `last_run_at`/`total_runs`/`successful_runs` on the `Workflow` update after each run.
- **FR-8 (US-5, history API):** Authenticated, user-scoped Founder OS endpoints list a
  user's workflows and a workflow's run history, and open one run's result/error. A failed
  run is clearly distinguishable with a human-readable reason.
- **FR-9 (US-2, visibility):** Founder OS surfaces which workflows exist and their status
  (n8n invisible by default); a link-out to the n8n editor for a workflow is the "advanced"
  affordance. (Embedded/SSO editor is **out of v1** unless O-5 says otherwise.)
- **FR-10 (minimal dashboard):** Dashboard affordance: list workflows, "run now", view run
  history + one run's result/error, and a link out to the n8n editor.

#### Non-functional (NFR)
- **NFR-1 (auth):** Every new Founder OS endpoint requires a valid Clerk JWT (`require_auth`)
  and scopes data to the authenticated user; a user only ever sees/operates their own
  workflows and runs (`standards/security.md`).
- **NFR-2 (callback auth — distinct surface):** n8n→Founder OS callbacks run **outside** the
  interactive Clerk session and MUST be authenticated and bound to the owning user without
  weakening the security model (no anonymous/unauthenticated agent execution; no privilege
  escalation across users). Mechanism is an **architecture + security decision** (O-2) — not
  chosen here.
- **NFR-3 (local-first / no paid dependency):** Runs against **self-hosted OSS n8n**; no
  managed/cloud n8n, no paid API required to prove the loop on a laptop.
- **NFR-4 (secret-safe config):** n8n base URL, API key/token, and the callback secret are
  environment-driven (`config.py` settings + `.env.example`), never logged, never committed.
- **NFR-5 (Alembic-only schema):** Any schema change (table creation for the existing ORM
  tables, plus any n8n-id column) goes through an Alembic migration, never hand-edited
  `schema.sql` (CLAUDE.md §5.8).
- **NFR-6 (provider-neutral):** Generation uses the existing pluggable LLM provider layer
  (Ollama default; Anthropic/Gemini/OpenAI-compatible swappable). No hard dependency on a
  specific provider; no dependency on a stubbed tool (`web_search`, `get_business_metrics`)
  for the v1 demo path — pick a demo workflow whose steps avoid stubs.
- **NFR-7 (approval integrity — hard safety):** 100% of HIGH-risk steps create an approval
  before acting; zero un-gated external/irreversible actions. Any miss is P0 (spec metric).
- **NFR-8 (verification):** End-to-end manual verification of the v1 loop is recorded
  (no repo-wide test runner exists; `standards/testing.md` — integration `test_*.py` hitting
  a live `:8000`, plus recorded manual n8n round-trip).

### 2. Milestones, tasks, and parallel tracks

Tasks are sized to be one execution unit each. **Track letters** group independent work that
can proceed in PARALLEL after the architecture gate (M0). `[dep: …]` marks prerequisites.

#### M0 — Architecture gate (BLOCKING; eng-architect, not executor)
Nothing below starts until M0 lands the ADR(s). This is the planner's hard gate.
- **A0** Resolve and record (ADR in `docs/decisions.md`) the four design decisions that
  every track depends on: IR/`steps` schema (O-1), callback auth mechanism (O-2),
  approval-gate placement in the round-trip (O-3), and n8n deployment mode + scheduler-of-
  record (O-4). Define the **n8n compile contract** and the **callback request/response
  contract**. Mandatory **eng-security** sign-off on O-2 + O-3 before execution. *Output:
  ADR + the two contracts the tracks code against.*

#### Track A — n8n infrastructure (PARALLEL) [dep: A0/O-4]
- **A1** Add self-hosted n8n to the dev stack: a service in `docker-compose.yml` (OSS image,
  pinned tag, healthcheck, named volume) wired into `start.sh` (start, wait-for-healthy,
  surface URL/logs) per O-4's default-vs-opt-in decision. *Config/infra only.*
- **A2** Add n8n connection + secret settings to `config.py` and `.env.example`
  (base URL, API key, callback base URL, callback secret) — secret-safe, no defaults that
  leak. *Config only.*

#### Track B — Data layer (PARALLEL) [dep: A0/O-1]
- **B1** Alembic migration that creates the existing workflow ORM tables (`workflows`,
  `workflow_executions`, `workflow_templates`, `tasks`, `task_dependencies` if not already
  migrated) and adds the n8n-workflow-identifier reference to `Workflow` (per O-1 / DB-1).
  *Migration only — no model redesign; tables already defined in `models.py`.*
- **B2** Thin persistence/query helpers for `Workflow` + `WorkflowExecution` (create,
  get-by-user, list-runs, update-run-counters) — user-scoped, reused by API + callback.
  *Depends on B1.*

#### Track C — n8n REST client (PARALLEL) [dep: A0 contract, A2 settings]
- **C1** A typed n8n REST client module (create/update/activate workflow, trigger run,
  read status as needed) using the existing httpx patterns; reads config from A2; secret-safe
  logging. *Pure client; no business logic.*

#### Track D — IR + compiler (PARALLEL) [dep: A0/O-1 IR schema]
- **D1** Orchestrator→IR generation: extend the orchestrate path so a recurrence-intended
  goal emits a persisted `Workflow` with a valid IR in `steps` (FR-1). Boundary for "persist
  as workflow vs one-shot" follows O-7 default (persist only when recurrence/scheduling/reuse
  is intended). *Depends on B2 for persistence.*
- **D2** IR→n8n JSON compiler: translate the IR (trigger + ordered agent/action steps) into
  n8n workflow JSON whose agent/action steps are **HTTP nodes that call the Founder OS
  callback** (FR-2/FR-5). Linear flows only (v1). *Depends on A0 compile contract + C1 to push.*

#### Track E — Callback API + auth (PARALLEL after security sign-off) [dep: A0/O-2, eng-security]
- **E1** Callback endpoint `app/api/<workflow>_routes.py` (registered in `main.py`) that n8n
  HTTP nodes hit to run a named agent/action step for the owning user, authenticated per O-2
  (service token / signed per-workflow secret — architect's call), user-scoped, returns the
  step result. Writes/updates the `WorkflowExecution` for the run (FR-5/FR-7). **Security-
  sensitive: external input + new auth surface — eng-security must review.**

#### Track F — Approval-gate integration (SEQUENTIAL after E1) [dep: E1, A0/O-3]
- **F1** In the callback step path, route HIGH-risk tool steps through the existing
  `ApprovalGate.check()`; on pending, implement the O-3 pause/resume (or poll) so n8n does
  not proceed until resolved; on **approve** execute, on **reject** halt the step and record
  status+reason on the run (FR-6, NFR-7). Reuse existing `/api/approvals/*` for the
  approve/reject UX. *This is the safety-critical task; needs the gate's new
  "wait-until-resolved" behavior — see RISK-2.*

#### Track G — Run-now + scheduling wiring (SEQUENTIAL) [dep: C1, D2, B2]
- **G1** "Run now" endpoint (Clerk-auth, user-scoped) that triggers the workflow's n8n run
  and creates a `WorkflowExecution` (FR-4a/FR-7).
- **G2** Cron scheduling: set `is_scheduled`/`schedule_cron`/`next_run_at` and push the cron
  to n8n so n8n fires the scheduled run (FR-4b). *n8n is the trigger of record per O-4.*

#### Track H — History/list API (PARALLEL with G) [dep: B2]
- **H1** Authenticated, user-scoped endpoints: list user's workflows (+status), list a
  workflow's runs, get one run's result/error (FR-8). Distinguish failed vs successful with
  a human-readable reason.

#### Track I — Dashboard UI (PARALLEL; back-end-contract-gated) [dep: H1, G1 shapes]
- **I1** Minimal dashboard (Next.js `apps/web`): list workflows, "run now", run history +
  one run's result/error, link-out to the n8n editor (FR-9/FR-10). Uses existing `useApi`;
  link-out only per O-5. *Can stub against agreed API shapes once H1/G1 contracts are fixed.*

#### M-final — Loop proof + verification (SEQUENTIAL; the gate)
- **V1** End-to-end dogfood: one founder goal → generated `Workflow` (D1) → compiled+pushed
  (D2/C1) → n8n runs and calls back (E1) → ≥1 HIGH-risk step routed through `ApprovalGate`
  with **both approve and reject verified** (F1) → `WorkflowExecution` written and visible in
  the dashboard (H1/I1). Record manual verification per NFR-8. *This satisfies the "Loop
  proven" success metric = v1 done.*

#### Parallel tracks summary (after M0 gate)
- **Independent, fully parallel:** A (infra), B (data), C (n8n client), D (IR/compiler — D1
  needs B2), H (history API).
- **Gated by security sign-off then parallel:** E (callback auth).
- **Sequential safety chain:** E1 → F1 (approval gate) → feeds V1.
- **Trigger wiring:** G after C/D/B.
- **UI:** I after H1/G1 contracts (can start against mocked shapes).

### 3. Critical path to the "loop proven" gate
A0 (ADR: IR + callback-auth + gate-placement contracts, with eng-security sign-off)
→ B1 (migration) → B2 (persistence) → D1 (generate IR) → D2 (compile to n8n JSON)
→ C1 (push to n8n) → E1 (authenticated callback) → **F1 (approval gate pause/resume,
approve+reject)** → G1 (run-now trigger) → V1 (end-to-end proof).

The two longest-pole items are **A0** (it blocks everything; the callback-auth and gate-
placement decisions need security review) and **F1** (it requires a new "wait-until-resolved"
behavior the current re-run-based gate does not have). Infra (A), history API (H), and UI (I)
are off the critical path and should be parallelized to absorb A0/F1 latency.

### 4. Risks & mitigations
- **RISK-1 — Callback auth weakens the security model (highest).** n8n callbacks run outside
  the Clerk session; a naive shared token or unauthenticated webhook could let anyone run
  any user's agents or escalate across users. *Mitigation:* O-2 is an ADR + **mandatory
  eng-security** sign-off in M0; per-workflow signed secret or scoped service token bound to
  `user_id`; secret-safe config (NFR-4); reject unsigned/expired callbacks; never trust
  `user_id` from the request body — derive it from the signed credential.
- **RISK-2 — Approval gate doesn't fit the round-trip.** The existing `ApprovalGate` is
  non-blocking/re-run-based; n8n needs a step to **pause until resolved** then continue.
  Forcing it could tempt a bypass (the spec's hard no). *Mitigation:* O-3 decided in M0
  (pause/resume the n8n run vs Founder-OS callback blocks/polls); F1 reuses
  `ApprovalGate.check/approve/reject` unchanged for the decision, adds only the wait
  mechanism; V1 explicitly verifies an **approve AND a reject** path; never let an n8n-side
  edit downgrade risk (gate is server-side, classification by tool name).
- **RISK-3 — n8n-side edits become an approval-gate escape hatch.** A founder (or attacker)
  edits the flow to call a HIGH-risk action without going through the callback. *Mitigation:*
  HIGH-risk actions execute **only** via the Founder OS callback/tool path that runs the gate;
  n8n nodes never hold the real action credentials; document this invariant in the ADR;
  eng-security verifies.
- **RISK-4 — IR contract churn.** The `steps` IR is the load-bearing contract shared by D1,
  D2, E1; if it shifts mid-build, three tracks rework. *Mitigation:* freeze the IR schema in
  A0 before tracks start; version it; tracks code to the frozen contract.
- **RISK-5 — n8n in the dev stack increases setup friction / footprint.** Could undercut the
  "runs on a laptop, zero cost" promise. *Mitigation:* O-4 decides default-vs-opt-in;
  pin the image, add a healthcheck, document the opt-in path; keep it OSS-only (NFR-3).
- **RISK-6 — Scheduling source-of-truth split.** If both APScheduler and n8n can fire
  workflows, runs could double-fire. *Mitigation:* O-4 makes **n8n the workflow trigger of
  record**; APScheduler stays only for the existing weekly planner; document the boundary.
- **RISK-7 — Generation reliability / stub dependency.** A generated flow may depend on a
  stubbed tool or produce an invalid IR. *Mitigation:* v1 demo workflow avoids stubs (NFR-6);
  validate the IR before compile; FR-3 actionable errors; the ≥70% reliability metric is a
  v1 target, not a v1 gate (the binary gate is "loop proven").
- **RISK-8 — Secret leakage in logs.** n8n token / callback secret printed in client or
  callback logs. *Mitigation:* NFR-4 secret-safe logging; eng-security checks C1/E1/A2.

### 5. Must go to eng-architect BEFORE execution (ADR-worthy — the M0 gate)
These block all tracks; resolve in M0 (A0). Items 1-3 require **mandatory eng-security**.
1. **O-1 — Canonical `steps` IR schema** (Orchestrator output ↔ n8n compiler contract).
   Load-bearing; freeze + version it. **Needs ADR.** Blocks D1/D2/E1.
2. **O-2 — Callback authentication & user-scoping** (service token vs signed per-workflow
   secret; how `user_id` is bound). **Needs ADR + mandatory eng-security.** Blocks E1/F1.
3. **O-3 — Where the approval gate sits in the n8n round-trip** (pause/resume the n8n run
   vs Founder-OS callback blocks/polls), given the existing gate is non-blocking/re-run-
   based. **Needs ADR + eng-security.** Blocks F1.
4. **O-4 — n8n deployment mode + scheduler-of-record** (default service vs opt-in in
   `docker-compose`/`start.sh`; confirm n8n is the single trigger of record so APScheduler
   isn't double-firing). Blocks A1/G2.
5. **O-5 — Editor surfacing for v1** (link-out vs embedded/SSO). Product leans link-out;
   architect to confirm — affects I1 scope. (Lower risk; confirm, don't over-design.)

Deferred to v2+ (flagged, **not** required for v1 execution): **O-6** edit-vs-regenerate
conflict rule (no auto-regen in v1, so it can't conflict yet), and the deeper part of **O-7**
workflow-vs-one-shot boundary (v1 uses the simple default: persist only when recurrence is
intended).

#### Known-stub dependency flag (per planner Never-list)
- The v1 demo path must **avoid** the known stubs `web_search` and `get_business_metrics`
  (`docs/requirements.md` known gaps; classified LOW-risk in `app/agents/approval.py`).
  Pick a demo workflow whose steps don't ground on mock data. If a generated workflow later
  depends on a stub, surface it as a known gap — do not fix it in this task (spec out-of-scope).

### 6. Definition of done (v1)
- [ ] **Loop proven (binary gate):** one founder goal → generated `Workflow` (IR in `steps`)
  → compiled + pushed to **self-hosted n8n** → n8n runs and calls back into a Founder OS
  agent → result visible in the Founder OS dashboard. Recorded manual verification (NFR-8).
- [ ] **Approval integrity:** ≥1 HIGH-risk step routed through the existing `ApprovalGate`,
  enforced server-side and **not** bypassable by an n8n edit; both an **approve** and a
  **reject** path verified end-to-end (reject halts the step + records reason).
- [ ] **Triggers:** manual "run now" and a cron schedule both fire a run via n8n;
  `is_scheduled`/`schedule_cron`/`next_run_at` and the run counters update.
- [ ] **Run records:** each run writes a `WorkflowExecution` with the required fields;
  `last_run_at`/`total_runs`/`successful_runs` update on the `Workflow`.
- [ ] **APIs:** all new endpoints require Clerk JWT and are user-scoped; a user only sees
  their own workflows/runs; failures surface human-readable reasons (no raw stack traces).
- [ ] **Local-first / secrets:** runs on self-hosted OSS n8n with no paid dependency; n8n +
  callback config is env-driven and secret-safe (nothing logged/committed); no v1 demo step
  depends on a known stub.
- [ ] **Schema via Alembic only**; ADR(s) for O-1/O-2/O-3 recorded in `docs/decisions.md`
  with eng-security sign-off; mandatory eng-security review completed (CLAUDE.md §7).
- [ ] Task moved to `tasks/completed/`, roadmap item updated (CLAUDE.md §7 step 8).

### Out of scope for this plan (mirrors product spec — restated for the executor)
Event/webhook trigger as a first-class path (v2), embedded/SSO n8n editor, in-product
drag-and-drop builder, template marketplace, workflow auto-evolution / self-rewrite,
conditional/branching/loop logic, multi-user/team-shared workflows, replacing tool stubs,
and managed/cloud n8n. Per-step streaming observability and the edit-vs-regenerate conflict
rule are v2.

### Next agent
→ **eng-architect**: resolve the M0 gate (O-1..O-5; ADR for O-1/O-2/O-3 in
`docs/decisions.md`), define the IR/compile + callback contracts, and pull mandatory
eng-security in on O-2/O-3 before any execution begins.

---

## Architecture  <!-- eng-architect; add an ADR to docs/decisions.md if significant -->

> Resolves the M0 gate. The decisions are recorded in **ADR-008** (`docs/decisions.md`,
> status `proposed` — **eng-security sign-off on O-2/O-3 is a hard gate before any execution**).
> This section is the buildable detail: exact contracts, data-model delta, API surface,
> file placement, the round-trip diagram, and the eng-security scrutiny list. All paths are
> absolute from the git root; product code lives under `founder-os/apps/api/app/`.
> Reuse-first; minimal; no gold-plating. The repo's monorepo root is
> `/Users/adityaastro/Documents/GitHub/founder-os/founder-os/`.

### O-1..O-5 resolutions (summary — full rationale in ADR-008)
- **O-1 IR:** `Workflow.steps` is `{"ir_version":1, "trigger":{...}, "steps":[node…]}` (see
  contract below). Both the Orchestrator's emit target and the compiler's sole input. Each
  agent/action node compiles to one n8n HTTP node that calls back into Founder OS by
  `step_id`; nodes hold no logic, no credentials, no `user_id`. Versioned by `ir_version`.
- **O-2 callback auth:** per-workflow **HMAC-signed token** bound to `user_id`, baked into
  each n8n HTTP node header at compile time. Server derives identity from the verified token /
  workflow owner — never from the body. Single-use per step + bounded `iat` = replay defence.
  Master secret only in `config.py`/`.env`.
- **O-3 gate placement:** **n8n Wait node ("resume on webhook")** after each risky step. The
  callback runs up to `ApprovalGate.check()`, parks n8n on pending, and a server-side resolver
  hook (keyed `approval_id → resume_url`) executes the approved tool then resumes n8n (or
  halts on reject). `ApprovalGate` is unchanged.
- **O-4 deployment + scheduler:** n8n is a **default docker-compose service** (pinned,
  healthchecked, profile-disable-able) and the **sole scheduler of record** for workflows;
  APScheduler stays weekly-planner-only.
- **O-5 editor:** **link-out** to `{N8N_BASE_URL}/workflow/{n8n_workflow_id}` for v1; no embed/SSO.

### Contract 1 — Canonical `steps` IR (frozen v1; `ir_version: 1`)
Stored in `workflows.steps` (JSONB). The Orchestrator emits exactly this; the compiler reads
exactly this. **Linear only** in v1 (`depends_on` = single-predecessor chain).

```jsonc
{
  "ir_version": 1,
  "trigger": {
    "type": "manual"                          // OR:
    // "type": "cron", "cron": "0 3 * * 1", "timezone": "Asia/Kolkata"
  },
  "steps": [
    {
      "id": "s1",                             // unique within the workflow; stable
      "type": "agent",                        // "agent" | "action"
      "agent": "research",                    // specialist slug (registry AGENT_CLASSES key)
      "instruction": "Summarise last week's support tickets.",
      "inputs": {},                           // optional static inputs / refs to prior step ids
      "depends_on": []                        // [] for first; ["s1"] for the next, etc.
    },
    {
      "id": "s2",
      "type": "action",
      "agent": "ops",                          // the agent context the tool runs under
      "tool": "send_slack_message",            // a real tool name from the ToolRegistry
      "arguments": { "channel": "#standup", "text": "{{s1.output}}" },
      "depends_on": ["s1"]
    }
  ]
}
```

- **Risk is derived server-side** from `tool` via `classify_tool_risk()` — the IR never
  declares a risk level (so an n8n edit cannot downgrade it). An `agent` step may itself call
  tools inside its run; those go through the gate on the agent's own execution path.
- **Validation (executor, before compile):** non-empty `steps`; unique `id`s; `agent` ∈
  registry slugs; `tool` ∈ ToolRegistry; `depends_on` references existing earlier ids; trigger
  is one of the two v1 shapes. Invalid IR → FR-3 actionable error, no push.
- **Versioning:** `ir_version` is mandatory; the compiler switches on it. A future shape bumps
  the integer; v1 code rejects unknown versions rather than guessing.

### Contract 2 — n8n compile target (per node)
The IR→n8n compiler (D2) emits an n8n workflow JSON with:
- One **trigger node**: Manual Trigger (always, for "run now" via REST) and, when
  `trigger.type == "cron"`, a **Schedule Trigger** node carrying the cron.
- Per IR step, one **HTTP Request node** → `POST {CALLBACK_BASE_URL}/api/workflows/callback`
  with body `{ "workflow_id": "<uuid>", "execution_id": "{{exec_id}}", "step_id": "s1" }`
  and header `X-FOS-Workflow-Token: <signed token>` (baked at compile time, per O-2). The
  `execution_id` is threaded from the trigger node's first callback response (the trigger node
  calls a `/start` callback that creates the `WorkflowExecution` and returns its id).
- After every HTTP node whose step *may* be MEDIUM/HIGH (i.e. every `action` node, and any
  `agent` node — conservative), a **Wait node in "resume on webhook" mode** (per O-3). For
  v1 the simplest correct shape is: put the Wait node after action nodes; if the preceding
  callback returned `status:"completed"` it resumes immediately, if `status:"awaiting_approval"`
  it parks until the resolver hits its resume-URL.
- n8n nodes hold **no** Founder OS tool credentials and **no** `user_id`. The only secret on
  the n8n side is the per-node signed token (an n8n credential), never the master secret.

### Contract 3 — Callback request/response (the n8n ↔ Founder OS wire)
All callbacks authenticate with `X-FOS-Workflow-Token` (O-2). Identity + workflow ownership
are derived from the verified token; the body is data only.

- `POST /api/workflows/callback/start` → body `{workflow_id}`; creates a `WorkflowExecution`
  (status `running`, `trigger_type` from caller), returns `{execution_id}`.
- `POST /api/workflows/callback/step` → body `{workflow_id, execution_id, step_id}`; loads the
  authoritative step from the persisted IR (not the body), resolves the user from the token,
  runs the step (agent run or single tool through the gate), updates the step + execution
  counters, returns one of:
  - `{ "status": "completed", "output": "...", "step_id": "s1" }`
  - `{ "status": "awaiting_approval", "approval_id": "...", "step_id": "s2" }` (and persists the
    n8n resume-URL passed by the Wait node so the resolver can resume)
  - `{ "status": "failed", "error": "human-readable", "step_id": "s3" }`
- `POST /api/workflows/callback/finish` (optional v1) → body `{workflow_id, execution_id,
  status}`; finalises the execution (`completed_at`, `duration_seconds`, `output_summary`,
  counters) and updates `Workflow` counters (`total_runs`, `successful_runs`, `last_run_at`).

The resolver (O-3) is **not** an n8n callback — it is an internal hook on the existing
`/api/approvals/{id}/approve|reject` path (or a subscriber to the approval resolution) that,
keyed by `approval_id`, executes the approved tool server-side and then calls the stored n8n
resume-URL with `{status, output}` (approve) or resumes the failure branch (reject).

### Data model delta (Alembic only — NFR-5; do NOT hand-edit `schema.sql`)
**Finding:** the `workflows`, `workflow_executions`, `workflow_templates`, `tasks`,
`task_dependencies` tables exist in BOTH `founder-os/apps/api/app/models.py` (ORM) and
`founder-os/apps/api/schema.sql` (DDL ~lines 94-153), but `alembic/versions/` is **empty**
(`alembic/env.py` targets `Base.metadata`; there are no version files). So a clean
Alembic-driven DB would NOT have these tables, while a `schema.sql`-seeded DB already does.
The migration must therefore be **idempotent / reconciling**, not a naive `create_table`.

**B1 migration (outline — do not write here, executor authors it):**
- Use `op.get_bind()` + an inspector (or `IF NOT EXISTS` guards) so the migration is safe on
  a DB already created from `schema.sql` (skip table creation when present; only add the new
  column). For a fresh DB it creates the five tables to match the ORM.
- **One genuinely new column** on `workflows`:
  - `n8n_workflow_id` `VARCHAR(255)` NULL — the n8n workflow identifier returned on push
    (FR-2). NULL until pushed; nullable, indexed for lookup by n8n id is optional (low volume).
- **No other new columns for v1.** Per-step status (the `awaiting_approval`/`completed`/
  `failed` per `step_id` and the parked n8n resume-URL + `approval_id`) is stored inside the
  existing JSONB: a `WorkflowExecution.triggered_by`/`output_summary` are reused, plus a
  `step_state` map persisted in `WorkflowExecution` — **reuse the existing
  `WorkflowExecution.triggered_by` JSONB is NOT semantically right; instead** add at most one
  JSONB column if a clean home is needed:
  - `WorkflowExecution.step_state` `JSONB` NULL — `{ "s1": {"status":"completed","output":...},
    "s2": {"status":"awaiting_approval","approval_id":"...","resume_url":"..."} }`. (Only add
    this if the executor confirms the existing columns can't carry it cleanly; prefer reuse.)
- Also reflect the ORM model change (`n8n_workflow_id`, and `step_state` if added) in
  `app/models.py` so `Base.metadata` and the migration agree (Alembic autogenerate will need
  the model to match). Keep `schema.sql` in sync as a secondary artifact per repo convention,
  but the **migration is authoritative** (NFR-5).

### API surface (new router `app/api/workflow_routes.py`, registered in `main.py`)
Mirror the sibling `*_routes.py` pattern (Pydantic models, `APIRouter(prefix=..., tags=...)`),
register in `founder-os/apps/api/app/main.py` (import ~lines 8-24, `include_router` ~85-101).

**User-facing (Clerk `require_auth`, user-scoped — NFR-1):** `prefix="/api/workflows"`
- `GET  /api/workflows` — list the caller's workflows (+ status, `n8n_workflow_id`, editor link). (FR-8/FR-9)
- `GET  /api/workflows/{id}` — one workflow (+ its IR summary + editor URL). (FR-9)
- `POST /api/workflows/{id}/run` — "run now": triggers the n8n run via the C1 client, creates a
  `WorkflowExecution`. (FR-4a/FR-7)
- `PATCH /api/workflows/{id}/schedule` — set `is_scheduled`/`schedule_cron`; recompiles + repushes
  the cron to n8n (n8n is trigger of record, O-4). (FR-4b)
- `GET  /api/workflows/{id}/runs` — run history for a workflow. (FR-8)
- `GET  /api/workflows/runs/{execution_id}` — one run's result/error. (FR-8)
- (Generation itself extends the existing `/api/agents/orchestrate` path — D1 — and does not
  add a new public "create workflow" endpoint; persistence happens inside the orchestrate flow
  when recurrence is intended, per O-7 default.)

**Callback (NOT Clerk — HMAC `X-FOS-Workflow-Token` per O-2; separate router or sub-prefix
`/api/workflows/callback`):**
- `POST /api/workflows/callback/start` — create execution, return `{execution_id}`.
- `POST /api/workflows/callback/step` — run one step (see Contract 3).
- `POST /api/workflows/callback/finish` — finalise execution.
- These MUST NOT use `require_auth`/`optional_auth` (no Clerk JWT in the round-trip) and MUST
  NOT honor the dev `x-test-user` header. They use a dedicated `require_workflow_callback`
  dependency that verifies the HMAC token and yields `(user_id, workflow)`.

All error responses: `HTTPException` with correct status + human-readable `detail` (FR-3);
no raw stack traces; secrets never in `detail` or logs (NFR-4).

### Module / folder placement (reuse-first; follow existing layout)
All under `founder-os/apps/api/app/`:
- `app/api/workflow_routes.py` — the new router (user-facing + callback endpoints). Registered in `main.py`.
- `app/workflows/` — new package (sibling to `crawler/`, `integrations/`, `retrieval/`):
  - `app/workflows/ir.py` — IR Pydantic models + `validate_ir()` (Contract 1). The frozen contract.
  - `app/workflows/compiler.py` — `compile_to_n8n(ir, callback_base, signer) -> dict` (Contract 2). Pure, no IO.
  - `app/workflows/n8n_client.py` — typed httpx client (create/update/activate/trigger; C1). Reads config; secret-safe logging.
  - `app/workflows/callback_auth.py` — HMAC sign/verify (O-2) + `require_workflow_callback` FastAPI dependency.
  - `app/workflows/service.py` — persistence/query helpers (B2): create workflow, get-by-user, list-runs, update counters, persist step_state. User-scoped.
  - `app/workflows/runner.py` — runs a single IR step: agent run via `AgentRegistry.get(...).run()` or a single tool call through `ApprovalGate`; the O-3 resolver hook. Reuses the registry + gate; no new agent logic.
- `app/config.py` — add settings (A2): `N8N_BASE_URL`, `N8N_API_KEY`, `WORKFLOW_CALLBACK_BASE_URL`, `WORKFLOW_CALLBACK_SECRET`.
- `founder-os/apps/api/.env.example` — document the four new vars (no real values).
- `app/agents/orchestrator.py` (or a thin helper it calls) — D1 generation: emit the IR + persist a `Workflow` when recurrence is intended. Extend the existing path; do **not** add a second entry point.
- `founder-os/docker-compose.yml` + `founder-os/start.sh` — add the pinned `n8nio/n8n` service (A1) per O-4.
- Frontend (I1): `founder-os/apps/web/app/(dashboard)/workflows/` page reusing `useApi`; link-out only.

### Integration points
- **Agents/registry:** `runner.py` calls `AgentRegistry(db, redis, settings).get(agent_slug, user_id=…, session_id=…).run(instruction)` — the same path `/api/agents/orchestrate` uses (`agent_routes.py:520-543`). No new agent class.
- **Tools:** `action` steps resolve a tool from the existing `ToolRegistry` and run it; risk via `classify_tool_risk()`.
- **Approval gate:** reuse `ApprovalGate(redis).check/approve/reject` **unchanged**; reuse `/api/approvals/*` for the founder UX. The only addition is the O-3 resolver hook keyed by `approval_id`.
- **Memory/event bus:** agent steps get memory/event-bus wiring for free via the registry; optionally publish `workflow.run.*` events on the existing `EventBus` for live dashboard updates (v2 nicety, not v1-required).
- **Celery/scheduler:** **n8n owns all workflow triggering** (O-4). APScheduler (`app/scheduler.py`) stays scoped to the weekly planner. If an individual step's agent run is long, the callback may enqueue it on Celery (`queue_routes.py` pattern) and have n8n poll/Wait — but for v1 keep callbacks synchronous unless a step exceeds a sane HTTP timeout; flag for executor.
- **Identity:** callback user resolution goes through `app/users.py:get_or_create_user_id` semantics (ADR-007) — but the input is the **token-bound user**, never a body field.

### Round-trip component diagram
```
Founder goal (free text)
   │  POST /api/agents/orchestrate  (Clerk require_auth)
   ▼
Orchestrator (app/agents/orchestrator.py)
   │  decompose → plan → (recurrence intended) emit IR
   ▼
IR (workflows.steps JSONB, ir_version:1)  ──validate──▶ app/workflows/ir.py
   │
   ▼
Compiler (app/workflows/compiler.py) ──build n8n JSON (HTTP nodes + Wait nodes,
   │                                    signed X-FOS-Workflow-Token baked per node)
   ▼
n8n REST client (app/workflows/n8n_client.py) ──create/activate──▶  ┌──────────────┐
   │   store returned n8n_workflow_id on Workflow                    │  self-hosted │
   │                                                                 │     n8n      │
   ▼                                                                 │ (docker svc) │
"Run now" (POST /api/workflows/{id}/run, Clerk) ──trigger──────────▶ │ cron+manual  │
                                                                     └──────┬───────┘
                                            n8n executes nodes, per step:   │
   ┌─────────────────────────────────────────────────────────────────────┘
   ▼  POST /api/workflows/callback/step   (X-FOS-Workflow-Token HMAC — NO Clerk)
Callback handler (app/api/workflow_routes.py + callback_auth.py)
   │  verify HMAC → derive user_id + workflow (NEVER from body)
   │  load authoritative step by step_id from persisted IR
   ▼
runner.py ──▶ agent run (AgentRegistry.get().run())  OR  single tool
                       │
                       ▼
              ApprovalGate.check()  (app/agents/approval.py — UNCHANGED)
                 │ LOW/MED auto    │ HIGH or "ask" → PendingApproval (Redis)
                 ▼                 ▼
            execute tool      return {status:"awaiting_approval", approval_id}
                 │                 │  persist resume_url → n8n Wait node parks
                 ▼                 ▼
        {status:"completed"}   Founder approves/rejects via /api/approvals/{id}/...
                 │                 │
                 │                 ▼  resolver hook (approval_id → resume_url)
                 │            approve: exec tool server-side → call n8n resume_url
                 │            reject:  halt step, record reason → resume failure path
                 ▼                 ▼
        WorkflowExecution row updated (status, counters, step_state, output_summary)
                 │
                 ▼
Founder OS dashboard (GET /api/workflows, /runs/{id}) + link-out to n8n editor
```

### Risks / trade-offs (architecture-level; build risks are in the Plan §4)
- **HMAC callback auth is the principal new attack surface** (RISK-1). Mitigated by: identity
  from token only, single-use-per-step replay defence, bounded `iat`, master secret only in
  env. This is the hard eng-security gate — see list below.
- **O-3 resolver introduces a new "execute-then-resume" server path** (RISK-2/RISK-3). Trade-off:
  more moving parts than a blocking call, but it keeps `ApprovalGate` unchanged and avoids
  long-held HTTP connections / bypass temptation. Invariant: HIGH-risk tools execute ONLY via
  this server-side gated path; n8n never holds real action credentials.
- **n8n Wait-node resume model couples us to an n8n feature.** Acceptable: it's a core OSS n8n
  capability; provider neutrality applies to *LLMs*, not the chosen workflow engine (n8n is a
  fixed product decision per the task).
- **Idempotent migration on a `schema.sql`-seeded DB** adds complexity (RISK noted in delta).
  Trade-off accepted: the repo has both `schema.sql` and empty `alembic/versions/`; the
  migration must reconcile, not assume a green field.
- **n8n as a default container** grows footprint (RISK-5). Mitigated by pin + healthcheck +
  compose-profile opt-out.

### Decisions needing founder/eng-security sign-off before execution
- **eng-security MUST sign off O-2 (callback HMAC) and O-3 (gate placement) before any of
  Tracks E/F start** (ADR-008 status is `proposed` until then). Items below are the precise
  scrutiny list.

### What eng-security must scrutinise (mandatory pass before E1/F1)
1. **HMAC token design (O-2):** signing scheme (`HMAC-SHA256`, per-workflow keyed secret),
   constant-time comparison (`hmac.compare_digest`), payload canonicalisation, `iat` skew
   bound, and that **`user_id` is NEVER read from the request body** — only from the verified
   token / workflow owner. Confirm a forged/replayed/expired token is rejected.
2. **Replay & single-use:** verify a step that is already `completed`/`failed`/
   `awaiting_approval` cannot be re-fired; that `execution_id` is validated to belong to the
   token's workflow + user; cross-workflow / cross-user token reuse is impossible.
3. **Secret handling (NFR-4):** `WORKFLOW_CALLBACK_SECRET` + `N8N_API_KEY` only in
   `config.py`/`.env`, never logged (audit `n8n_client.py`, `callback_auth.py`, `workflow_routes.py`),
   never returned in any response `detail`. The per-node token stored in n8n must not expose the master secret.
4. **Approval-gate integrity (O-3, NFR-7):** confirm HIGH-risk tools cannot execute without an
   approval; the resolver only executes on an `approved` resolution it itself verifies (not on
   a body claim); a `reject` halts and records, never silently proceeds; the gate is reused
   unchanged and classification is server-side by tool name (no n8n-side downgrade — RISK-3).
5. **n8n-edit escape-hatch (RISK-3):** verify that editing the n8n flow (adding a node, changing
   a URL, removing the Wait node) cannot cause a HIGH-risk real-world action, because the only
   path that holds credentials + executes tools is the server-side gated callback.
6. **Callback endpoints are NOT Clerk and NOT dev-bypassable:** confirm `require_auth`/
   `optional_auth` and the `x-test-user` dev bypass are absent from the callback path.
7. **Resume-URL trust:** the n8n resume-URL is stored server-side and only ever called by the
   server; confirm it can't be supplied by an attacker to redirect/poison the resume.

## Build notes  <!-- eng-executor -->
- _(deferred — execution begins only after eng-security signs off O-2/O-3 and ADR-008 is accepted)_

## Review findings  <!-- eng-reviewer -->
- _(deferred)_

## QA results  <!-- eng-qa -->
- _(deferred)_

## Security report  <!-- eng-security; REQUIRED — touches auth, secrets, approval gate, external input -->
- _(deferred — REQUIRED pass before Tracks E/F. Scrutiny list defined in the Architecture
  section above. This change touches the approval gate, introduces n8n→Founder OS callbacks
  (external input + new HMAC auth surface), and new secrets (n8n credentials + callback
  secret). Security review is mandatory per CLAUDE.md §7 and is a hard gate on ADR-008.)_

## Security Review (ADR-008)  <!-- eng-security; pre-execution design audit -->

> Audit of the ADR-008 *design* (no code yet) against `standards/security.md`,
> `skills/security_audit.md`, and the 3-tier model in `docs/requirements.md`. Read the
> real primitives: `app/auth.py`, `app/agents/approval.py`, `app/api/approval_routes.py`,
> `app/config.py`, `app/main.py`. Scrutiny items 1-7 from the Architecture handoff are
> addressed inline. Each finding names the exact control and where it must be enforced.

### Verdict: **PASS WITH CONDITIONS**

The architecture is sound on the highest-risk axes: identity is token-derived (never
body-derived), risk is classified server-side by tool name from the persisted IR,
n8n holds no credentials, and the callback path is off Clerk and off the dev bypass.
ADR-008 may move to **accepted** and Tracks E/F may begin **only once the BLOCKING
findings below are written into the ADR/contracts as hard requirements**, because
several controls the verdict depends on are asserted in prose but not yet pinned in a
way an executor cannot accidentally violate. The conditions are enforceable at build
time and must be verified by a second eng-security pass on the E1/F1 diff (per
CLAUDE.md §7) before V1.

---

### BLOCKING (must be fixed in the ADR/contract before execution starts)

**B-1 — MEDIUM-risk `action` steps will AUTO-EXECUTE with NO approval. The design's
"Wait node after every action node" does NOT gate them.**
Where: `app/agents/approval.py:447-459` (`ApprovalGate.check`, default `ask` branch) vs
Architecture "Contract 2 / Contract 3" (`callback/step`) and ADR-008 O-3.
Risk: The real `ApprovalGate.check()` auto-approves LOW **and MEDIUM** risk when the
user's preference is the default `"ask"` (lines 447-459: *"MEDIUM → auto-approve (agent
autonomy)"*). The design assumes the callback "runs the step up to the gate" and parks
on `awaiting_approval`, but for a MEDIUM-risk tool (e.g. `gcal_create_event`,
`gcal_delete_event`, `create_task`, `save_draft`) `check()` returns
`approved=True, auto_approved=True` and the runner will EXECUTE the tool inline in the
`callback/step` handler and return `status:"completed"`. The n8n Wait node then resumes
immediately. So an externally-visible MEDIUM action (creating/deleting a calendar event
on the founder's real Google Calendar) fires inside an unattended n8n cron run with no
human in the loop. The design text ("a step that *may* invoke a MEDIUM/HIGH-risk tool …
parks") materially misrepresents how the gate actually behaves for MEDIUM. This is the
exact "no path executes an externally-visible action without the intended control"
clause of `standards/security.md` and the 3-tier model in `docs/requirements.md`.
Required fix (pick one, record in ADR-008 O-3):
  (a) Define the v1 invariant that MEDIUM-risk tools inside an *unattended workflow run*
      are treated as gated (i.e. the callback step must force MEDIUM through a pending
      approval regardless of the per-user `ask`/`always_allow` default), because the
      founder is not present at cron time; OR
  (b) Explicitly scope v1 `action` steps to LOW-risk tools only and reject any IR whose
      `action.tool` classifies MEDIUM/HIGH at validation time, deferring gated MEDIUM
      actions to a later increment.
Either way the ADR must stop claiming the Wait node gates MEDIUM — it does not. Do NOT
"solve" this by setting `always_allow` for the founder; that path is also auto-approve
and removes the human entirely. (HIGH is correctly always-gated at `approval.py:419-429`,
so HIGH is not affected by this finding — only MEDIUM is the gap.)

**B-2 — `agent`-type steps can execute HIGH-risk tools INSIDE the agent run, bypassing
the per-step Wait node entirely; the resume/approval round-trip for that case is
undefined.**
Where: Architecture "Round-trip diagram" + Contract 1 note ("An `agent` step may itself
call tools inside its run; those go through the gate on the agent's own execution path")
vs `runner.py` design ("agent run via `AgentRegistry.get().run()`").
Risk: When a HIGH-risk tool is invoked *during* an agent's own `.run()` (not as a
top-level `action` node), `ApprovalGate.check()` correctly returns a `PendingApproval`
(no bypass) — but the agent run is happening synchronously inside the `callback/step`
HTTP handler with no n8n Wait node bound to *that* inner approval. The design only places
Wait nodes around top-level nodes. The result is one of: (i) the agent treats the gate's
"pending" as a tool failure and continues/hallucinates a result, or (ii) the HTTP handler
blocks/holds the connection (the exact anti-pattern O-3 was written to avoid), or (iii)
the inner pending approval is created but nothing ever resumes it, so it silently expires
(Redis TTL `DEFAULT_PENDING_TTL = 3600`, `approval.py:242`) and the run is recorded as
completed-without-the-action. None of these is safe or specified.
Required fix (record in ADR-008 O-3 + Contract 3): define exactly how an
*inside-agent-run* HIGH/MEDIUM pending approval surfaces back to n8n. Acceptable v1
options: (a) for v1, agent steps run in a "no-side-effect" mode — the agent may only call
LOW-risk tools, and any MEDIUM/HIGH tool it attempts is converted to a top-level
`action` step / surfaced as `awaiting_approval` to the callback so the Wait node parks;
or (b) the callback detects any pending approval produced anywhere in the step
(inner or top-level), persists its `approval_id` + resume_url, and returns
`awaiting_approval` — the runner must propagate inner pendings, not swallow them. The
must-not-happen outcome to state explicitly: an inner HIGH-risk tool must never execute,
and must never silently no-op while the run reports success.

**B-3 — The O-3 "resolver" must re-derive risk and the approval decision server-side at
resume time; it must NOT trust the stored `approval_id`/resume_url as proof of approval,
and must verify the resolution is `approved` from Redis (not from a webhook body).**
Where: Architecture "Contract 3 / resolver" + ADR-008 O-3 (resolver "executes the
now-approved tool server-side") vs `approval.py:340-372` (`resolve`) and
`approval_routes.py:135-172` (`approve`).
Risk: The resolver is the new code path that actually executes the HIGH-risk tool after
approval. If it executes based on being *called* (e.g. anyone who can hit the resolver
hook, or a replayed approve event) rather than on re-reading the `PendingApproval` from
Redis and confirming `status == "approved"` AND that the approval belongs to the same
token-bound `user_id` AND maps to this `execution_id`/`step_id`, then a forged or
replayed resolution executes a HIGH-risk real-world action. Note `resolve()` keeps the
approved record only 300s (`approval.py:360`) — the resolver must run inside/atomically
with the approve path, or re-fetch and verify before the record expires.
Required fix (record in ADR-008 O-3): the resolver MUST (1) be triggered only from the
authenticated `/api/approvals/{id}/approve` path (which is already `require_auth` +
ownership-checked at `approval_routes.py:152-155`), (2) re-load the approval and assert
`status=="approved"`, (3) re-classify the tool risk server-side and re-confirm the
arguments came from the persisted IR/PendingApproval (not from the n8n resume payload),
and (4) bind execution to the stored `execution_id`+`step_id` so a resume cannot be
redirected to a different step. State this as the resolver's preconditions in the ADR.

**B-4 — `WORKFLOW_CALLBACK_SECRET` has no minimum-entropy / generation / rotation
requirement, and `config.py` defaults every secret to `""`. A blank or weak callback
secret silently forges all callbacks.**
Where: `app/config.py:9-81` (every secret defaults to `""`, e.g. `STRIPE_SECRET_KEY`,
`OAUTH_STATE_SECRET`) + ADR-008 O-2 ("key length/entropy" is named in the scrutiny list
but not pinned).
Risk: Following the existing config pattern, `WORKFLOW_CALLBACK_SECRET: str = ""` would
default empty. An empty/short secret means an attacker can compute a valid
`X-FOS-Workflow-Token` for any `workflow_id`+`user_id` and drive the callback to run any
user's agents (privilege escalation across users — RISK-1). HMAC is only as strong as the
key. The ADR also names "rotation story" but does not define one.
Required fix (record in ADR-008 O-2 + A2): (1) `WORKFLOW_CALLBACK_SECRET` must be
required at startup when `APP_ENV != "development"` — fail fast (refuse to boot / refuse
to compile a workflow) if it is empty or shorter than 32 bytes of entropy; do not ship a
usable default. (2) Document generation (`secrets.token_urlsafe(32)`+) in
`.env.example` as a placeholder only (never a real value). (3) Rotation: since the
per-node token is `HMAC(secret+":"+workflow_id, payload)`, rotating the master secret
invalidates every already-pushed n8n token — the ADR must state that rotation requires
recompiling+repushing all active workflows (or support a key-id/`kid` in the token so two
secrets can be valid during rollover). Pick one and write it down so executors don't
discover it in prod.

---

### CONDITIONS (must be implemented exactly this way in E1/F1; verified on the diff)

**C-1 — Callback single-use / replay must be enforced with an atomic, race-safe
state transition, not a read-then-write.**
Where: ADR-008 O-2 ("each `WorkflowExecution` is single-use per `step_id`") +
`runner.py`/`service.py` design.
Two concurrent fires of the same `(execution_id, step_id)` (n8n retry, duplicate cron,
attacker replay) must not both execute. A check-then-set on the JSONB `step_state` map is
a TOCTOU race that can double-fire a HIGH-risk action. Enforce with an atomic guard: a
conditional UPDATE that flips the step to `running` only `WHERE` it is currently in a
runnable state (DB row-level, returning rowcount), or a Redis `SET NX` lock keyed by
`(execution_id, step_id)`. The callback proceeds only if it won the transition; otherwise
it returns the existing terminal state. State this in Contract 3.

**C-2 — `execution_id` binding must be verified against the token's workflow AND user on
every `callback/step` and `callback/finish`, server-side.**
Where: ADR-008 O-2 (d). The handler must load the `WorkflowExecution`, assert its
`workflow_id == token.workflow_id` and its owning `user_id == token-derived user_id`, and
reject (404/403, no detail leak) on mismatch. This is what prevents a valid token for
workflow A being used to drive an execution of workflow B / another user. The `step_id`
must also be confirmed to exist in the persisted IR (authoritative step loaded by id, per
O-1) — never trust step content from the body.

**C-3 — HMAC verification must use `hmac.compare_digest` (constant-time) and a canonical,
unambiguous payload encoding.**
Where: ADR-008 O-2 / `callback_auth.py` design. Required: (1) `hmac.compare_digest` for
the signature comparison (never `==`); (2) deterministic canonicalization of the payload
before signing/verifying — e.g. `json.dumps(payload, sort_keys=True,
separators=(",",":"))` or a fixed field order — so the signed bytes are reproducible and
not subject to key-ordering/whitespace ambiguity; (3) verify the signature BEFORE parsing
or trusting any payload field; (4) reject tokens whose decoded `workflow_id` ≠ the loaded
workflow. Because the per-workflow key is `WORKFLOW_CALLBACK_SECRET + ":" + workflow_id`,
confirm a token minted for workflow A cannot verify against workflow B (it can't, given
the key derivation — but add an explicit test for cross-workflow token rejection).

**C-4 — `iat` bound + clock-skew handling.** O-2's 30-day `iat` window is acceptable
ONLY because the token is additionally single-use-per-step (C-1) and execution-bound
(C-2); document that dependency. Reject tokens with `iat` in the future beyond a small
skew (e.g. 60s) and `iat` older than the bound. The token is long-lived by necessity
(baked at compile time, used by cron months later), so single-use + execution-binding —
NOT `iat` — is the real replay defense; the ADR must say so plainly so no one weakens
single-use thinking `iat` covers replay.

**C-5 — Secret-safe logging and error surface (NFR-4) — enforce at three sites.**
Where: `n8n_client.py`, `callback_auth.py`, `workflow_routes.py` (E1), plus the resolver.
(1) Never log `WORKFLOW_CALLBACK_SECRET`, `N8N_API_KEY`, the per-node token, or the n8n
resume_url (it can carry an n8n resume key). (2) Never put any of these in an
`HTTPException(detail=...)` — the design already mandates human-readable detail; add
"no token/secret/resume_url in detail". (3) The `PendingApproval.description`
(`approval.py:517-567`) and `arguments` are echoed to the founder via
`/api/approvals/pending`; confirm no workflow callback secret is ever stuffed into
`arguments`/`description`. (4) On HMAC failure return a generic 401/403 with a fixed
message — do not echo the received token or say which check failed (no enumeration oracle).

**C-6 — Callback endpoints stay off Clerk AND off the dev bypass — verify structurally.**
Where: `app/auth.py:137-151` (`_dev_test_user` is gated on `APP_ENV=="development"` and
fires inside BOTH `require_auth` and `optional_auth`) + `app/main.py:104-105`.
The callback router MUST depend on `require_workflow_callback` ONLY — it must not import
or depend on `require_auth`/`optional_auth` (otherwise in `development` an `x-test-user`
header would authenticate a callback with an arbitrary user_id and skip HMAC entirely).
Equally, `require_workflow_callback` must NOT contain any `APP_ENV=="development"` shortcut
of its own — HMAC is verified in all environments. Add a test asserting the callback
rejects (a) no token, (b) `x-test-user` header with no token, (c) a Clerk Bearer JWT
(should be ignored, not accepted) — i.e. the only accepted credential is a valid HMAC.

**C-7 — Resume-URL is server-stored, server-called, and validated; never attacker-
suppliable as an open redirect / SSRF sink.**
Where: ADR-008 O-3, Contract 3 (resume_url "passed by n8n in the Wait node's payload",
persisted to step_state, called by the resolver).
The resume_url arrives in a callback body, so it IS attacker-influenced if the token is
ever weak/forged. Conditions: (1) persist it only after the callback's HMAC + execution
binding pass (C-2/C-3); (2) before the resolver calls it, validate the host/scheme
against the configured `N8N_BASE_URL` (allowlist — reject any resume_url whose origin is
not the known n8n instance) to prevent the approved-action result being POSTed to an
attacker host (SSRF / result exfiltration); (3) the resolver calls it server-side only,
never returns it to a client, never logs it (C-5). State the allowlist check in the ADR.

**C-8 — IR validation must reject any attempt to smuggle risk control into the IR, and
must reject unknown `ir_version`.** Where: O-1 Contract 1 validation. Risk is derived only
via `classify_tool_risk(tool)` server-side; the validator must (1) ignore/forbid any
risk-like field in the IR, (2) confirm `action.tool` ∈ ToolRegistry and `agent` ∈ registry
slugs (an unknown tool defaults to MEDIUM at `approval.py:170`, which under B-1 must be
gated), (3) reject `ir_version` it doesn't understand rather than guessing. This is what
makes "an n8n edit cannot downgrade risk" actually true: confirm the callback re-reads the
tool name from the **persisted IR by step_id**, never from the n8n request body (Contract 3
already says this — make it a tested assertion).

---

### Scrutiny-list disposition (architect's items 1-7)
1. HMAC token design — sound in shape; **conditions C-3, C-4; blocker B-4** (entropy/
   rotation/no-default). Cross-user/cross-workflow confusion is prevented by the key
   derivation + C-2 binding.
2. Replay & single-use — **condition C-1** (must be atomic/race-safe, not read-then-write)
   and **C-2** (execution binding). `iat` alone is insufficient (C-4).
3. Secret handling — **condition C-5**; **blocker B-4** for the secret's own strength.
4. Approval-gate integrity — **blockers B-1 (MEDIUM auto-exec), B-2 (inside-agent HIGH),
   B-3 (resolver must verify approval from Redis, not trust the call)**. HIGH at the
   top-level `action` path is correctly no-bypass (`approval.py:419-429`).
5. n8n-edit escape hatch — design is correct IN PRINCIPLE (n8n holds no credentials; risk
   classified server-side from persisted IR by tool name). Holds only if B-1/B-2 and C-8
   are enforced; otherwise an edit that swaps a LOW step's `tool` or adds an action node is
   still gated by server-side classification, which is the right property — confirm via C-8.
6. Callback endpoints auth — **condition C-6**; design correctly keeps them off Clerk and
   off the dev bypass, but this must be enforced structurally + tested.
7. Resume-URL trust — **condition C-7** (allowlist against `N8N_BASE_URL`; server-only).

### Residual risks to track (accept for v1, revisit in v2)
- **R-1 n8n compromise / n8n DB readable:** the per-node tokens live in n8n. Anyone who
  can read n8n's credential store gets long-lived (30-day `iat`) callback tokens for those
  workflows. Single-use-per-step limits the blast radius to not-yet-run steps; document
  that hardening n8n's own auth/secrets is in scope for the deployment (O-4) — pin a
  version with known-good security defaults, do not expose n8n's editor publicly.
- **R-2 Approval TTL vs cron latency:** `DEFAULT_PENDING_TTL = 3600` (`approval.py:242`).
  A workflow that parks on approval at 3am will have its pending approval expire in 1h; the
  n8n Wait node may park far longer. Define behavior (the ADR says timeout → mark failed,
  no silent proceed — good); ensure the resolver treats an expired/absent approval as
  "reject/halt", never "approve".
- **R-3 No rate-limiting on callback endpoints:** unauthenticated-at-network-edge endpoints
  invite brute-force of the HMAC. With a strong secret (B-4) this is infeasible, but add
  basic rate-limiting / fail-closed on repeated bad tokens in v2.

### Required before ADR-008 → accepted and before Tracks E/F start
- B-1, B-2, B-3, B-4 written into ADR-008 (O-2/O-3) and the callback/IR contracts as hard
  requirements (not prose). 
- C-1…C-8 recorded as the E1/F1 build checklist.
- A second eng-security pass on the E1/F1 implementation diff (CLAUDE.md §7) before V1 —
  the design PASS does not substitute for the code-level review of the new auth surface.

**Blockers go back to eng-executor (via eng-architect to amend ADR-008).**

## Security Re-Review (ADR-008 amendments)  <!-- eng-security; DESIGN re-review of B-1..B-4 fixes -->

> Re-audit of the amended ADR-008 (`docs/decisions.md` — O-1-AMEND, O-2-AMEND,
> O-3-AMEND-1/2/3, "Conditions for execution" C-1..C-8, "Residual risks" R-1..R-3)
> against my four original BLOCKING findings (B-1..B-4) from the "Security Review
> (ADR-008)" section above. This is a **DESIGN** re-review only — it confirms the
> blockers are closed at the design level so ADR-008 can move `proposed` → `accepted`
> and Tracks E/F can start. It is NOT the code-level review; that still happens on the
> E1/F1 diff. Re-verified against the real primitives: `app/agents/approval.py`,
> `app/api/approval_routes.py`, `app/auth.py`.

### Verdict: **PASS — ADR-008 may move from `proposed` to `accepted`.**

All four BLOCKING findings (B-1..B-4) are genuinely closed at the design level. The
amendments do not paper over the gate's real behavior — they correct the earlier prose
error (the Wait node does NOT gate MEDIUM) and replace it with a hard, server-side IR
rule that forbids non-LOW `action` tools, plus a no-side-effect agent-step mode, a
verify-from-Redis resolver, and a fail-fast strong-secret rule. C-1..C-8 are the correct
and sufficient build checklist; one clarification is added to C-1 below (no new blocker).

**The only remaining security gate is the code-level eng-security re-review of the
E1/F1 implementation diff** (per CLAUDE.md §7), which must verify C-1..C-8 are
implemented exactly as written. The design PASS does not substitute for that pass.

---

### Per-blocker determination

**B-1 — MEDIUM `action` auto-execute unattended — CLOSED.**
Resolved by **O-1-AMEND** (decisions.md lines 73-96) + **C-8** + **O-3-AMEND-1**.
- The fix is the correct option (b) from my original finding: v1 `action` steps are
  **LOW-risk-tool only**. `validate_ir()` MUST reject any `action.tool` that does not
  classify `RiskLevel.LOW` under `classify_tool_risk()` (O-1-AMEND.1). Because unknown/
  MCP tools default to MEDIUM (`approval.py:170`), they are rejected too — no silent
  MEDIUM slipping through.
- Critically, the rule is **re-enforced server-side at execution**: `callback/step`
  re-reads the tool name from the **persisted IR by `step_id`** (never the n8n body) and
  re-classifies; non-LOW for an `action` step → `status:"failed"`, no execution
  (O-1-AMEND.3). This makes an n8n-side tool swap fail closed. That is the property that
  makes the closure real, not merely a validation-time check that an edit could bypass.
- The ADR now explicitly retracts the false claim that the Wait node gates MEDIUM
  (O-1-AMEND closing note + O-3-AMEND-1). Good — that was the root misrepresentation.
- **Is "LOW-risk only" actually safe to run unattended?** Yes, for the v1 LOW set.
  I re-checked `TOOL_RISK_MAP` (`approval.py:121-156`): the LOW tools are read-only /
  internal-context (`search_knowledge`, `list_tasks`, `get_*`, `gcal_list_events`,
  `gcal_get_event`, `check_calendar_conflicts`, `store_working_memory`, etc.). None has
  an external irreversible side effect; `store_working_memory` is internal state.
  `web_search`/`get_business_metrics` are LOW *and* stubs (avoid per the planner's
  stub-flag, but not a safety risk). So LOW = side-effect-free enough to run with no
  human present. The one durable caveat (already a CONDITION, C-8): the LOW guarantee is
  only as good as the classification, which is **derived from the tool name server-side
  on the persisted IR** — never declared in the IR (O-1-AMEND.2) — so it cannot be
  downgraded by an n8n edit. That is exactly the right invariant.
- Residual (correctly accepted, not a blocker): MEDIUM/HIGH top-level `action` nodes are
  **out of v1 scope** and deferred to the v2 gated Wait-node path. Acceptable because v1
  cannot emit them (validator rejects) and cannot execute them (re-classify rejects).

**B-2 — HIGH/MEDIUM tool firing INSIDE an agent run, unbound to any Wait node — CLOSED.**
Resolved by **O-3-AMEND-2** (decisions.md lines 174-196).
- The fix adopts the stronger of my two suggested options: agent steps run in
  **no-side-effect mode** — "agent steps may only perform content/analysis; any tool
  call above LOW is refused/deferred, never executed inline." The enforcement point is
  concrete: `app/workflows/runner.py` constrains the toolset / risk ceiling passed to the
  agent run, and the minimal v1 realization is explicit and verifiable — **the
  workflow-agent toolset is filtered to LOW-risk tools so the agent literally cannot
  invoke a non-LOW tool.** That is a real mechanism (capability removal), not a prompt
  request, so it is not hand-wavy.
- The must-not-happen invariant is stated verbatim and correctly: "an inner MEDIUM/HIGH
  tool must never execute inline during an agent run, and the run must never report
  success while having silently no-op'd a side-effecting tool." The deferred-tool signal
  path (convert to a step-boundary `awaiting_approval` bound to a real Wait node /
  resume-URL, persist `approval_id`+resume_url+`execution_id`+`step_id`) closes the
  "silent expiry of an orphaned inner pending" hole (the TTL-3600 swallow I flagged).
- Note for the executor (verified on the diff, not a design blocker): if v1 ships the
  minimal "filter the toolset to LOW only" form, the agent simply cannot raise a deferred
  MEDIUM/HIGH signal — which is safe (fail-closed) and matches the v1 scope reduction. The
  full deferred-signal → `awaiting_approval` path is only exercised if a real-world action
  is later authored as its own top-level step. Either realization satisfies the invariant.

**B-3 — Resolver must verify approval from Redis, not trust being called — CLOSED.**
Resolved by **O-3-AMEND-3** (decisions.md lines 198-224), six preconditions.
- (1) Fires **only** from the authenticated, ownership-checked
  `/api/approvals/{id}/approve` path — re-confirmed at `approval_routes.py:139` (`require_auth`)
  and `:152-155` (`approval.user_id != user_id` → 404). It is an internal hook, NOT a
  network-reachable endpoint and NOT an n8n callback. Correct.
- (2) Re-loads the `PendingApproval` from Redis and asserts `status == "approved"` before
  executing anything; absent/expired/`rejected` → reject/halt, never approve. Correct —
  matches `resolve()` semantics (`approval.py:340-372`).
- (3) Re-classifies risk server-side (`classify_tool_risk`) and takes tool name +
  arguments from the persisted PendingApproval / IR, **never from the n8n resume body**.
  Correct — the resume body is data for n8n only.
- (4) Binds execution to stored `execution_id`+`step_id` and confirms the approval's
  `user_id` matches the execution owner. Closes resume-redirection.
- (5) The **300s approved-record TTL race is explicitly handled**: the resolver runs
  atomically with / synchronously inside the approve path so verification happens while
  the approved record still exists (`approval.py:360` = 300s), and a **late approval**
  (record expired / Wait node already timed out) is a **no-op halt** — record the step
  `failed` ("approval expired / window elapsed"), never execute against a stale approval.
  This is the precise race I flagged; it is now defined and fail-closed.
- (6) Resume-URL host/scheme allowlisted against `N8N_BASE_URL` before the resolver calls
  it (C-7) — closes the SSRF/exfil sink. Correct.

**B-4 — Weak/blank/defaulted callback secret + no rotation story — CLOSED.**
Resolved by **O-2-AMEND** (decisions.md lines 119-142).
- (1) **Fail-fast, no usable default.** `WORKFLOW_CALLBACK_SECRET` MUST NOT default to a
  usable value; when `APP_ENV != "development"` the app refuses to start (and the compiler
  refuses to compile/push) if the secret is empty or < 32 bytes of entropy (>=43 chars for
  `token_urlsafe(32)`). The check is a startup validator on `Settings` (pydantic validator
  or lifespan assert) — fail closed, not a warning. This directly closes the
  "`: str = ""` default silently forges all callbacks" hole I cited. Correct and concrete.
- (2) Generation documented in `.env.example` as a **placeholder only** (never a real
  value) with `python -c "import secrets; print(secrets.token_urlsafe(32))"`; never
  logged, never returned. Correct.
- (3) **Rotation story is chosen, not left open:** the **`kid` (key-id) scheme** is the
  v1 default — payload carries `kid`, server holds `kid → secret` (primary +
  `WORKFLOW_CALLBACK_SECRET_PREVIOUS` rollover slot), verification selects by `kid`, and
  rotation is add-new-kid → keep-old-during-window → recompile+repush → retire-old. An
  explicit documented fallback exists if `kid` is descoped (rotating the master secret
  invalidates all baked tokens → REQUIRES recompile+repush of every active workflow, must
  be in the runbook + an operator warning, never silently leaving dead workflows). A
  concrete choice with a documented fallback — closed.

---

### C-1..C-8 confirmation (correct + sufficient build checklist)

C-1..C-8 as written in ADR-008 (decisions.md lines 245-293) are the correct and complete
set of conditions for the executors to implement for the E1/F1 diff. They map 1:1 to the
original conditions and now carry the amendment hooks (C-8 ties to O-1-AMEND's non-LOW
rejection; C-6 to the dev-bypass structural concern; C-7 to the SSRF allowlist). I verified
the structural premise behind C-6 is real: `_dev_test_user` (`app/auth.py:137-151`) is
gated on `APP_ENV=="development"` and fires inside BOTH `require_auth` and `optional_auth`,
so a callback router that depended on either would accept an `x-test-user` header in dev and
skip HMAC — C-6's "depend on `require_workflow_callback` ONLY, no `APP_ENV` shortcut" is the
right defense.

One clarification to add to C-1 (refinement, **not** a new blocker) — to be verified on the
diff: the C-1 atomic single-use guard must also cover the **agent-step deferral path**
(O-3-AMEND-2) and the **resolver execution** (O-3-AMEND-3.5), not only `callback/step`
entry. I.e. the transition a step → terminal (`completed`/`failed`) when the resolver runs
the deferred/approved tool must itself be atomic against a concurrent re-fire or a late
resume, so an approve + a Wait-node-timeout cannot both act on the same `(execution_id,
step_id)`. C-1's "atomic state transition, never read-then-write" already implies this;
make it explicit for the resolver/deferral paths in the E1/F1 implementation. No ADR change
required to accept; flag for the code review.

### Residual risks (R-1..R-3) — accepted for v1, unchanged
R-1 (n8n credential-store compromise → long-lived `iat` tokens; blast radius bounded by
single-use-per-step), R-2 (approval TTL 3600 vs cron latency; defined as timeout→fail, never
silent proceed — now backed by O-3-AMEND-3.5), and R-3 (no callback rate-limiting; strong
secret makes brute-force infeasible, add in v2) are correctly scoped as accepted-for-v1 and
revisit-in-v2. No objection.

---

### Gate decision
- **B-1, B-2, B-3, B-4: all CLOSED at the design level.**
- **ADR-008 may move `proposed` → `accepted`.** Execution (Tracks E/F and the rest) may begin.
- **Remaining security gate:** the **code-level eng-security re-review of the E1/F1
  implementation diff** (CLAUDE.md §7), which must verify C-1..C-8 are implemented exactly
  as written — with specific attention to: C-1 atomicity extended to the resolver/deferral
  paths (clarification above); C-6 structural absence of `require_auth`/`optional_auth` and
  any `APP_ENV` shortcut on the callback router; O-1-AMEND.3 server-side re-classification
  from the persisted IR (the tested "n8n edit cannot downgrade risk" assertion); O-2-AMEND.1
  fail-fast startup validator; and O-3-AMEND-3 resolver preconditions (verify-from-Redis,
  300s-window handling, resume-URL allowlist).

**No blockers remain at the design level. Verdict: PASS.**

---

## Execution — Track B: backend foundation + data layer (eng-executor, 2026-06-18)

> Scope-limited slice: the shared contract layer (IR + validation + serializer),
> the data-model delta, the reconciling Alembic migration, the config additions +
> fail-fast validator, the `.env.example` placeholders, and user-scoped persistence
> helpers. **status: review** for THIS slice only — the broader task (Tracks A/C/D/E/F/G/H/I)
> remains open; the file frontmatter is intentionally left as-is. Hand off to eng-reviewer.

### Files changed
- `founder-os/apps/api/app/workflows/__init__.py` — new package docstring.
- `founder-os/apps/api/app/workflows/ir.py` — frozen v1 IR (Pydantic models +
  `validate_ir` + `parse_ir`/`serialize_ir`/`get_step`). O-1-AMEND hard rules.
- `founder-os/apps/api/app/workflows/service.py` — user-scoped persistence helpers
  (create/get/list/set-n8n-id for Workflow; create/get/list/update for WorkflowExecution).
- `founder-os/apps/api/app/models.py` — `Workflow.n8n_workflow_id` (String(255) NULL) +
  `WorkflowExecution.step_state` (JSONB NULL).
- `founder-os/apps/api/app/config.py` — `N8N_BASE_URL`, `N8N_API_KEY`,
  `WORKFLOW_CALLBACK_BASE_URL`, `WORKFLOW_CALLBACK_SECRET`,
  `WORKFLOW_CALLBACK_SECRET_PREVIOUS` + `@model_validator` fail-fast (O-2-AMEND/B-4).
- `founder-os/apps/api/.env.example` — "Workflow callbacks (Track B)" block (mid-file,
  away from the EOF region a parallel agent uses for the Track A n8n block).
- `founder-os/apps/api/alembic/versions/0001_workflow_engine.py` — new reconciling migration.
- `founder-os/apps/api/schema.sql` — synced (secondary) the two new columns.
- `founder-os/apps/api/test_workflow_ir.py` — 16 unit tests for `validate_ir`.

### IR shape (v1, `ir_version: 1`)
Envelope `{ir_version, trigger, steps}`. `trigger` = `{type:"manual"}` or
`{type:"cron", cron, timezone}`. `agent` node:
`{id, type:"agent", agent, instruction, inputs, depends_on}`. `action` node:
`{id, type:"action", agent, tool, arguments, depends_on}`. All models `extra="forbid"`.

### `validate_ir` rules (O-1-AMEND)
Reject unknown `ir_version`; LOW-only `action` tools via `classify_tool_risk` (reused, not
duplicated) — MEDIUM/HIGH/unknown rejected; reject any smuggled risk-like field; `agent` ∈
registry slugs; unique ids; single-predecessor `depends_on` referencing earlier ids; non-empty
steps. `get_step` loads the authoritative tool/agent from the persisted IR by id (C-2/C-8).

### Migration approach (idempotent / reconciling)
`alembic/versions/0001_workflow_engine.py` (`down_revision=None`). Inspector-guarded: creates
each `workflow*` table only when ABSENT and its FK deps (`users`/`agents`/`workflow_templates`)
exist (green-field), then add-if-missing for the two new columns — safe on a schema.sql-seeded
DB (skips creation, adds columns) and on a fresh ORM build. `users`/`agents` are left to the
base schema (out of Track B scope). Downgrade only drops the two additive columns. The
migration is authoritative; schema.sql synced secondarily (CLAUDE.md §5.8).

### Verification (no live DB / no server, per task constraint)
- `python3 test_workflow_ir.py` → **16 passed, 0 failed** (LOW passes; MEDIUM/HIGH/unknown
  rejected; unknown ir_version rejected; smuggled `risk` rejected; round-trip stable).
- `alembic heads` / `alembic history` → single head `0001_workflow_engine` from `<base>`.
- Migration import-validated (revision/down_revision/upgrade/downgrade present).
- Config validator exercised: dev empty OK; prod empty/short raise; prod strong OK.
- `app.models` + `app.workflows.service` import cleanly; new columns mapped.

### Flagged (no design change made)
- Added `WorkflowExecution.step_state` (JSONB NULL) per the ADR data-model delta: the
  existing `triggered_by` JSONB is the run-trigger payload, NOT a per-step status sidecar
  (ADR explicitly calls it "NOT semantically right"). `step_state` is the clean home for
  per-step status / approval_id / resume_url and the target of the C-1 atomic transition.
- `N8N_BASE_URL` / `N8N_API_KEY` added to `config.py` (needed by the SSRF allowlist + n8n
  client) but their `.env.example` lines were intentionally NOT added — the parallel Track A
  agent owns the "# n8n (Track A)" block at EOF; the config defaults are safe placeholders.
- models.py vs schema.sql were already in sync for the pre-existing workflow tables; the only
  reconciliation needed was adding the two new columns to both (done).

---

## Execution — Wave 2a: n8n REST client + IR→n8n compiler (eng-executor, 2026-06-18)

> Scope-limited slice (Tracks C1 + D2 ONLY): the typed async n8n REST client and the pure
> IR→n8n-JSON compiler, plus unit tests. Did NOT touch orchestrator.py, the workflow router,
> models, config, schema.sql, or any callback/auth code (other waves own those). **status:
> review** for THIS slice only; the broader task stays open. Hand off to eng-reviewer.

### Files changed (all under founder-os/apps/api/)
- `app/workflows/n8n_client.py` — NEW. Typed async n8n REST client (`N8nClient`) over the n8n
  public API (`/api/v1`). Reuses `app/agents/api_client.APIClient` (async httpx + timeouts +
  retry/circuit-breaker + sensitive-header redaction) — no second HTTP stack. Auth via the
  `X-N8N-API-KEY` header from `Settings.N8N_API_KEY`; base URL from `Settings.N8N_BASE_URL`.
  Methods: `create_workflow`, `activate_workflow`, `deactivate_workflow`, `trigger_workflow`,
  `health`, `from_settings`, `aclose` + async-context-manager. Typed errors: `N8nError`,
  `N8nAuthError`, `N8nNotFoundError`, `N8nUnavailableError`. The API key is never logged and
  never appears in a raised message (C-5).
- `app/workflows/compiler.py` — NEW. Pure `compile_ir_to_n8n(workflow_id, ir, *, user_id,
  callback_base_url, sign_token_fn) -> dict`. No IO. Consumes the real IR types from
  `app/workflows/ir.py`. Emits: Manual Trigger (always) + Schedule Trigger (cron, O-4); a
  Start callback HTTP node (`/api/workflows/callback/start`); one HTTP node per IR step
  (`/api/workflows/callback/step`) with the per-node signed token in `X-FOS-Workflow-Token`
  via the injected `sign_token_fn`; a Finish callback node (`/api/workflows/callback/finish`);
  linear `depends_on` → sequential connections. The master secret never enters the JSON; the
  only secret baked is the opaque per-node token from `sign_token_fn`. `user_id` is passed to
  `sign_token_fn` only, never written into any node body (identity is token-derived, O-2).
- `test_workflow_compiler.py` — NEW. 19 standalone unit tests (no live n8n/LLM/DB).
- `test_n8n_client.py` — NEW. 15 standalone unit tests using `httpx.MockTransport`.

### sign_token_fn contract (the dependency Wave 3 / callback-auth track MUST satisfy)
HMAC is implemented in Wave 3, NOT in the compiler. The compiler depends on an injected:

    SignTokenFn = Callable[[workflow_id: str, user_id: str, step_id: str | None], str]

- Returns the exact opaque header value for `X-FOS-Workflow-Token` on a single n8n HTTP node.
  Per ADR-008 O-2: `base64(payload).hmac_sha256` with `payload = {workflow_id, user_id, iat,
  kid}`, key = `WORKFLOW_CALLBACK_SECRET[kid] + ":" + workflow_id`.
- `step_id` is `None` for the start/finish boundary nodes and the concrete step id otherwise.
  Wave 3 MAY single-use-bind the token per step (C-1) or mint a workflow-scoped token and rely
  on server-side execution/step binding (C-2) — the compiler is agnostic.
- MUST raise if the master secret is absent/weak at compile time (O-2-AMEND #1); the compiler
  propagates that to the caller (FR-3). MUST NEVER return the master secret or the plaintext
  user_id (C-5) — only the opaque token lands in n8n.

### n8n JSON shape emitted (node types)
`{name, nodes[], connections{}, active:false, settings:{executionOrder:"v1"}}`.
Node types used: `n8n-nodes-base.manualTrigger`, `n8n-nodes-base.scheduleTrigger` (cron only),
`n8n-nodes-base.httpRequest` (start, per-step, finish). HTTP nodes use `sendHeaders` +
`headerParameters` for the token and a JSON `jsonBody` whose `execution_id` is an n8n
expression (`={{ $json.execution_id }}`) threaded from the Start node's response.

### Verification (no live server / no live n8n, per task constraint)
- `python3 test_workflow_compiler.py` → **19 passed, 0 failed** (manual→ManualTrigger;
  cron→ScheduleTrigger carrying `0 3 * * 1`; one /callback/step node per step + start + finish;
  every callback URL built from callback_base_url and host.docker.internal form, no localhost;
  X-FOS-Workflow-Token present on every node via the fake signer; master secret AND plaintext
  user_id absent from the JSON; linear chain wired).
- `python3 test_n8n_client.py` → **15 passed, 0 failed** (request method/path; X-N8N-API-KEY
  sent; create returns id for top-level and nested shapes; activate/deactivate endpoints;
  401/403→Auth, 404→NotFound, 5xx/connect→Unavailable, 422→generic; API key never in any
  raised message).
- Both modules import cleanly (`app.workflows.n8n_client`, `app.workflows.compiler`).

### Flagged design gaps (no design change made — flagged per scope)
- **Wait-node machinery NOT emitted in v1.** Per O-3-AMEND-1, v1 has no gated step (the IR
  validator forbids non-LOW `action` tools and agent steps run no-side-effect), so the compiler
  emits no n8n Wait nodes. They are the v2 home for gated MEDIUM/HIGH actions and require the
  resolver + resume-URL plumbing (O-3-AMEND-2/3). Do not add Wait nodes without that. Flagged
  in the compiler module docstring.
- **`trigger_workflow` uses `POST /api/v1/workflows/{id}/run`.** Some n8n deployments expose
  manual runs only via a workflow's webhook trigger node; if Track A's pinned n8n image differs,
  the run-now wiring (Track G) may need to route through the webhook node instead. Confirm
  against the deployed n8n version.
- **`execution_id` threading** assumes n8n passes the Start node's JSON response (`{execution_id}`)
  downstream via `$json`. With multiple linear HTTP nodes, Track G/E should confirm the
  `$json` reference resolves to the Start response (or switch to a referenced-node expression,
  e.g. `$('FOS Start').item.json.execution_id`). Left as the simple `$json` form for v1; flagged
  for the callback/run wiring wave.
- **No config/.env changes made** — `N8N_BASE_URL`, `N8N_API_KEY`, `WORKFLOW_CALLBACK_BASE_URL`
  already exist in `config.py` (added by Track B). The client reads them via `from_settings`.


---

## Wave 2b — Orchestrator workflow IR generation (eng-executor)

> Scope built: Track D1 (generation only) per ADR-008 US-1 + O-1-AMEND. Does NOT
> include the n8n client (C1), compiler (D2), callback API (E1), or workflow router —
> those remain owned by other waves/agents. Compile + push to n8n is Wave 3.

### What was built
- **`app/workflows/generator.py`** — provider-neutral IR generation.
  - `generate_workflow_ir(llm, goal, *, available_agents=None, available_low_risk_tools=None, context=None) -> ir_dict`
    Prompts an `LLMProvider` (any provider; default Ollama) for STRICT JSON in the v1 IR
    schema, parses tolerantly (prose-wrapped JSON recovered, mirroring
    `app/agents/generator.py`), and ALWAYS runs `validate_ir`. On failure it repair-prompts
    ONCE with the validation errors fed back, then raises `WorkflowGenerationError` (carries
    the validation messages for an FR-3 actionable error). An invalid IR is never returned.
  - `default_low_risk_tools()` derives the action-step tool menu by classifying the agents'
    declared tools via `classify_tool_risk` server-side — the prompt can only ever offer
    LOW-risk tools (defence-in-depth alongside `validate_ir`; O-1-AMEND #1 / C-8).
  - `DEFAULT_WORKFLOW_AGENTS` = registry specialist slugs minus `orchestrator`.
- **`app/agents/orchestrator.py`** — added `OrchestratorAgent.generate_and_persist_workflow(db, goal, *, name=None, description=None, context=None) -> Workflow`.
  Thin, additive (does NOT touch the `run()` loop). Uses `self.llm` + `self.user_id`,
  generates a validated IR, and persists via `service.create_workflow(...)` with
  `n8n_workflow_id=None`. Sets `is_scheduled`/`schedule_cron` from a cron trigger.

### How the LLM is constrained to LOW-risk / real-agent IR
- System prompt hard-rules: only the provided agent slugs; action steps only with the
  provided LOW-risk tool list; linear `depends_on` chain; trigger ∈ {manual, cron}; no
  risk fields. The provided menus are derived server-side (`classify_tool_risk`), so the
  model is never offered a non-LOW tool or a fake agent.
- `validate_ir` is the load-bearing gate — the prompt is only a steer. Even a caller that
  passes a wider `available_low_risk_tools` is filtered to LOW server-side before prompting.

### Validation-failure handling
- Parse failure or `validate_ir` errors → one repair attempt (errors fed back) → if still
  invalid, raise `WorkflowGenerationError` with the messages. Never persists an invalid IR.

### Verification (provider-neutral stub LLM, no live server, no real calls)
- `cd founder-os/apps/api && source .venv/bin/activate && python3 test_workflow_generator.py`
  → **16 passed, 0 failed**: good IR returned + validated; prose-wrapped JSON recovered;
  HIGH (`send_email`) rejected; MEDIUM (`create_task`) rejected; bad agent slug rejected;
  non-JSON rejected; repair path (bad→good) succeeds in 2 calls; empty goal rejected before
  any LLM call.
- `python3 test_workflow_ir.py` → still **16 passed, 0 failed** (no regression).

### Where Wave 3 plugs in (generate → compile → push → run)
- Call `OrchestratorAgent.generate_and_persist_workflow(db, goal, ...)` (or
  `generate_workflow_ir` directly) from the workflow API / orchestrate path when a founder
  asks to automate a recurring goal. It returns a persisted `Workflow` with a valid IR in
  `steps` and `n8n_workflow_id=None`.
- Then Wave 3: `compile_to_n8n(workflow.steps, ...)` (D2) → push via the n8n REST client
  (C1) → record the returned id with `service.set_n8n_workflow_id(...)`.

### Files changed
- `founder-os/apps/api/app/workflows/generator.py` (new)
- `founder-os/apps/api/app/agents/orchestrator.py` (added `generate_and_persist_workflow`)
- `founder-os/apps/api/test_workflow_generator.py` (new test)
