# Architecture Decision Records — Founder OS

> A running log of significant technical decisions and their rationale, so the
> system never re-litigates a settled question or loses the "why". The
> [architect agent](../agents/architect.md) appends an ADR whenever a decision
> shapes the architecture. Newest first.

## Format (one entry per decision)

```
## ADR-NNN — <short title>
- Date: YYYY-MM-DD
- Status: proposed | accepted | superseded by ADR-MMM
- Context: what forced a decision (the problem, constraints).
- Decision: what we chose.
- Consequences: trade-offs, what this rules out, follow-ups.
- Links: tasks/, code, related ADRs.
```

---

## ADR-009 — The Company State Engine becomes the moat; n8n demoted to optional execution

- Date: 2026-06-22
- Status: accepted
- Context: The product's headline differentiator was *auto-generated workflows* executed via
  self-hosted n8n (ADR-008 / task 004). That framing makes the **execution substrate** the
  moat. The deeper, more defensible founder pain is **fragmentation**: Slack knows the
  conversation, GitHub the code, Stripe the revenue, Obsidian/Notion the docs — but **no
  system knows the company**, so the founder app-switches all day. A thin wrapper that only
  generates workflows does not own that problem; a canonical model of company state does.
- Decision: Reposition Founder OS around a **Company State Engine** — a structured, canonical,
  non-decaying model of the company (goals, projects, tasks, decisions, metrics, people,
  meetings, notes) fed by **passive multi-channel observation** and surfaced **where the
  founder already works** (Obsidian first, Notion later), wrapped in the **five loops**
  (Observe → Remember → Understand → Execute → Learn). The engine is fed by three provenance-
  tagged feeds: `observed` (tool adapters), `user_doc` (founder-provided docs), and `system`
  (agent-written memories + Hermes procedural skills). A **hygiene system** (write-gate,
  provenance trust-weighting, dedup-on-ingest, decay/composite-scoring, periodic Curator)
  keeps it useful and not bloated. **n8n is demoted, not deleted:** dynamic in-process AOV
  graphs (the existing Orchestrator) are the default execution model; n8n remains an optional,
  invisible execution backend under the State Engine. ADR-008 stays valid; only its
  *positioning* (the moat → an optional sub-layer) changes.
- Consequences:
  - The State Engine is a **fourth, distinct** layer alongside `knowledge_items` (RAG),
    `memory_pages`/`memory_links` (temporal KG), and the 4-layer agent memory — authoritative
    *normalized* state vs. the *recall* substrate. Ingestion feeds both; do not reinvent the
    existing memory/RAG machinery.
  - New tables (Alembic): `state_sources`, `state_observations`, `company_state_entities`,
    `state_relations`. Designed so the `user_doc`/`system` feeds and the Curator need no schema
    change to land later.
  - First slice = State Engine core + **Obsidian** bidirectional sync (engine owns a managed
    `FounderOS/` subfolder; rest of vault read-only observed). Local-first, no OAuth.
  - Roadmap reprioritized: State Engine is the flagship (`now`/`next`); task 004 (n8n) moves to
    `later`/optional. The readme, vision, and architecture are reframed accordingly.
  - Rules out positioning n8n as the differentiator; rules out a two-way destructive vault
    merge in v1; defers the full Curator + Hermes skills + non-Obsidian adapters to later
    phases.
- Links: docs/superpowers/specs/2026-06-22-company-state-engine-design.md,
  tasks/backlog/011-company-state-engine.md, ADR-008, readme.md, docs/vision.md,
  docs/architecture.md, docs/roadmap.md.

---

## ADR-008 — n8n-backed auto-workflow system: IR, callback auth, gate placement, deployment

- Date: 2026-06-18 (amended 2026-06-18 to resolve eng-security BLOCKING findings B-1..B-4)
- Status: **accepted** (2026-06-18) — the eng-security RE-review of amendments B-1..B-4
  returned **PASS** (recorded in the task file's "## Security Re-Review (ADR-008 amendments)"
  section); all four BLOCKING findings are closed at the design level. **Amendments B-1..B-4
  are complete** (written below as hard requirements in O-1/O-2/O-3 + the "Conditions for
  execution" and "Residual risks" subsections). The original verdict was PASS WITH CONDITIONS.
  The only remaining security gate is a second eng-security pass on the E1/F1 *code* diff
  (per CLAUDE.md §7), which must verify C-1..C-8 are implemented as written before V1 ships.
- Context: task 004 makes the readme's headline promise real — a founder states a goal, the
  Orchestrator auto-generates a workflow, it is compiled to n8n workflow JSON, pushed to a
  self-hosted n8n via REST, and n8n executes it (cron + manual + HTTP-callback nodes that call
  back into Founder OS agents). The fixed decision is that n8n is *invisible* execution +
  visualization infrastructure; the founder never wires a flow by hand. Five load-bearing
  design questions block every build track (the planner's M0 gate): O-1 the canonical `steps`
  IR, O-2 callback authentication outside a Clerk session (highest risk), O-3 where the
  non-blocking `ApprovalGate` sits in the n8n round-trip, O-4 deployment mode + scheduler of
  record, O-5 editor surfacing. Constraints: reuse the existing `Workflow`/`WorkflowExecution`
  tables and `ApprovalGate`/`/api/approvals/*` (do not rebuild), Alembic-only schema, provider-
  neutral, self-hosted OSS n8n, approval gate enforced server-side and never bypassable by an
  n8n-side edit. **Amendment context (2026-06-18):** the pre-execution eng-security design
  audit (recorded in the task file's "Security Review (ADR-008)" section) returned PASS WITH
  CONDITIONS and raised four BLOCKING findings that the verdict depended on but which were only
  asserted in prose. The root cause of B-1/B-2 is a verified property of the real
  `ApprovalGate.check()` (`app/agents/approval.py`): on the default `ask` preference it
  **auto-approves LOW *and* MEDIUM** risk (lines 447-459, "MEDIUM → auto-approve (agent
  autonomy)"); **only HIGH is always gated** (lines 419-429). Unknown tools default to MEDIUM
  (`classify_tool_risk`, line 170). Pending-approval Redis TTL is 3600s (line 242); the
  approved-record TTL after `resolve()` is 300s (line 360). The approve path is
  `require_auth` + ownership-checked (`approval_routes.py:152-155`). These facts force the
  scope reductions and hard rules in the amended O-1/O-2/O-3 below.

- Decision:

  **O-1 — Canonical `steps` IR (v1, versioned).** `Workflow.steps` (JSONB) stores a single
  envelope `{"ir_version": 1, "trigger": {...}, "steps": [ ... ]}`. `trigger` is one of
  `{"type":"manual"}` or `{"type":"cron","cron":"<5-field>","timezone":"Asia/Kolkata"}` (v1;
  `webhook`/`event` reserved for v2). Each entry in `steps` is one node:
  `{"id":"s1","type":"agent","agent":"<slug>","instruction":"<text>","inputs":{...},
  "depends_on":["s0"]}` for an agent step, or `{"id":"s2","type":"action","tool":"<tool_name>",
  "arguments":{...},"agent":"<slug>","depends_on":["s1"]}` for a direct risk-classified tool
  action. v1 is **linear** (`depends_on` is a single-predecessor chain; branching is v3). The IR
  is the Orchestrator's output target AND the compiler's only input — neither side reads n8n
  JSON. Every `agent` and `action` node compiles to exactly one n8n **HTTP Request node** that
  POSTs to the single Founder OS callback endpoint with `{workflow_id, execution_id, step_id}`;
  n8n nodes carry **no agent logic, no tool credentials, and no `user_id`** — Founder OS derives
  identity and re-reads the authoritative step from the persisted IR by `step_id`. The IR is
  frozen and versioned by `ir_version` so D1/D2/E1 code against a stable contract (RISK-4);
  any future shape change bumps `ir_version` and the compiler branches on it.

  **O-1-AMEND — IR validation hard rules (resolves B-1, supports B-2 / C-8). Enforced at IR
  validation (`app/workflows/ir.py:validate_ir`) AND re-enforced server-side at
  `callback/step` by re-reading the tool name from the persisted IR and re-classifying via
  `classify_tool_risk()` — never from the n8n request body.** Because the real gate
  auto-approves MEDIUM on the default `ask` preference, an unattended cron run could fire a
  MEDIUM tool with no human present. v1 therefore narrows what the IR may contain:
  1. **`action` steps are LOW-risk only.** `validate_ir()` MUST reject any IR whose
     `action.tool` does not classify as `RiskLevel.LOW` under `classify_tool_risk(tool)`.
     A tool that classifies MEDIUM or HIGH (including any unknown/MCP tool, which defaults to
     MEDIUM at `approval.py:170`) is a validation error → FR-3 actionable error, no compile,
     no push. MEDIUM/HIGH real-world actions in v1 must come through the gated Wait-node path
     as their own step ONLY via the mechanism in O-3-AMEND-1; if that mechanism is not yet
     built, they are **out of scope for v1**.
  2. **Risk is never declared in the IR.** The validator MUST reject (or strip and ignore)
     any risk-like field in a node; risk is derived only server-side by tool name (C-8).
  3. **Server-side re-classification at execution.** `callback/step` loads the step from the
     persisted IR by `step_id`, reads `tool` from that persisted IR (not the body), calls
     `classify_tool_risk(tool)`, and if the result is not LOW for an `action` step it returns
     `status:"failed"` with a human-readable reason — it does NOT execute. This makes an
     n8n-side edit that swaps in a non-LOW tool fail closed.
  4. **Unknown `ir_version` is rejected**, not guessed (C-8).
  This is the precise rule that replaces the earlier (incorrect) prose claiming the Wait node
  gates MEDIUM. The Wait node does not gate MEDIUM; the IR validator does, by forbidding
  non-LOW `action` tools.

  **O-2 — Callback auth via per-workflow HMAC-signed token bound to `user_id` (no Clerk).**
  n8n callbacks run outside an interactive Clerk session, so they authenticate with a
  stateless HMAC, NOT a Clerk JWT and NOT the dev `x-test-user` header. At workflow-compile
  time Founder OS mints a per-workflow secret and the compiler bakes, into each HTTP node's
  header, a signed token `t = base64(payload).hmac` where `payload = {workflow_id, user_id,
  iat, kid}` and the signature is `HMAC-SHA256(key = WORKFLOW_CALLBACK_SECRET[kid] + ":" +
  workflow_id, msg = canonical(payload))`. The callback endpoint (a) verifies the HMAC with the
  server-side secret (constant-time `hmac.compare_digest`, signature checked BEFORE any payload
  field is trusted — C-3), (b) loads the `Workflow` row, (c) confirms the token's `workflow_id`
  matches and **derives `user_id` from the verified token / the workflow's owner — never from
  the request body** (per `standards/api.md`), (d) enforces that the body's `execution_id`
  belongs to that workflow + user (C-2). Replay protection: each `WorkflowExecution` is
  single-use per `step_id` via an **atomic state transition** (C-1) — a step that is already
  `completed`/`failed`/`awaiting_approval`/`running` rejects a re-fire — and the callback only
  accepts executions in a runnable state; `iat` older than a bounded skew (e.g. 30 days, >
  longest cron interval) or in the future beyond a small skew (60s) is rejected. The signing
  key (`WORKFLOW_CALLBACK_SECRET`) lives only in `config.py`/`.env` (NFR-4), is never logged,
  and n8n stores only the derived per-node header value (an n8n credential), never the master
  secret. This is provider-neutral and adds no new dependency (`hmac`/`hashlib`/`secrets`
  stdlib).

  **O-2-AMEND — secret strength, no-default, and rotation (resolves B-4). Enforced in
  `config.py` (A2) + `app/workflows/callback_auth.py` + documented in `.env.example`.**
  1. **No usable default; fail-fast.** `WORKFLOW_CALLBACK_SECRET` MUST NOT default to a usable
     value. When `APP_ENV != "development"` the app MUST refuse to start (and, defensively,
     the compiler MUST refuse to compile/push a workflow) if the secret is empty or shorter
     than **32 bytes of entropy** (≥43 chars for `token_urlsafe(32)`). In `development` a
     missing secret is allowed only for non-callback flows; any attempt to compile a workflow
     still requires a present secret. The check is a startup validator on `Settings` (e.g. a
     pydantic validator or an explicit `assert` in the lifespan) — fail closed, not a warning.
  2. **Documented generation.** `.env.example` documents the var with a **placeholder only**
     (never a real value) and the generation command `python -c "import secrets;
     print(secrets.token_urlsafe(32))"`. Never logged, never returned in any response.
  3. **Rotation via key-id (`kid`).** The token payload carries a `kid` and the server holds a
     small map of `kid → secret` (`WORKFLOW_CALLBACK_SECRET` is the current/primary `kid`;
     `WORKFLOW_CALLBACK_SECRET_PREVIOUS` is an optional rollover slot). Verification selects
     the secret by the token's `kid`. Rotation procedure: add the new secret as the primary
     `kid`, keep the old `kid` valid during a rollover window, recompile+repush active
     workflows so new tokens use the new `kid`, then retire the old `kid`. This avoids a hard
     "rotate the master secret → every baked n8n token instantly breaks" cliff. (If the `kid`
     scheme is descoped by the executor for v1, the fallback rule is explicit: rotating
     `WORKFLOW_CALLBACK_SECRET` invalidates ALL baked n8n tokens and REQUIRES a
     recompile-and-repush of every active workflow — this MUST be documented in the runbook
     and surfaced as an operator warning, never silently leaving dead workflows.) The chosen
     v1 default is the **`kid` scheme** because it makes rotation a non-outage operation.

  **O-3 — Approval gate via n8n pause + resume-on-approval webhook (gate unchanged).** The
  existing `ApprovalGate.check()` is non-blocking/re-run based and there is no "block until
  resolved" primitive — and adding a long-blocking HTTP handler would hold connections and
  invite a bypass. Decision: keep `ApprovalGate.check/approve/reject` **unchanged**. The
  compiler places, immediately after each HTTP node that may invoke a HIGH-risk tool, an
  n8n **Wait node in "resume on webhook" mode**. Flow per gated step: (1) the callback runs the
  step up to the gate; (2) `check()` returns a pending `PendingApproval`; (3) the callback
  persists the n8n resume-URL (passed by n8n in the Wait node's payload) onto the step's record,
  sets the `WorkflowExecution`/step state to `awaiting_approval`, and returns to n8n which now
  parks on the Wait node — **the action has not executed**; (4) the founder approves/rejects via
  the existing `/api/approvals/{id}/approve|reject`; (5) the resolver (O-3-AMEND-3) executes the
  now-approved tool server-side on **approve** and then calls the n8n resume-URL with the
  result, or on **reject** halts the step (records status + reason) and resumes n8n down a
  failure path. The gate's HIGH-risk no-bypass guarantee is untouched; risk is classified
  server-side by tool name, so an n8n-side edit cannot downgrade it (RISK-3). If n8n's
  resume-URL is unreachable the execution times out and is marked failed (no silent proceed).

  **O-3-AMEND — what actually gets gated, agent-step scope, and the resolver's preconditions
  (resolves B-1 gate-placement, B-2, B-3).**

  - **O-3-AMEND-1 — Only HIGH-risk *top-level `action`* tools take the gated Wait-node path,
    and (v1) there are none, because O-1-AMEND forbids non-LOW `action` tools.** The Wait
    node exists for HIGH-risk top-level actions; in v1 the IR validator rejects HIGH (and
    MEDIUM) `action` tools, so the only place a HIGH-risk tool can legitimately arise in v1
    is *inside an agent run* — handled by O-3-AMEND-2. The Wait-node compile machinery is
    still built (it is the v2 home for gated MEDIUM/HIGH actions) but in v1 the only
    `awaiting_approval` path that can occur is the agent-step deferral of O-3-AMEND-2. The ADR
    no longer claims the Wait node gates MEDIUM — it does not; the IR validator forbids
    MEDIUM/HIGH `action` tools instead (B-1).

  - **O-3-AMEND-2 — `agent` steps run in NO-SIDE-EFFECT mode (resolves B-2).** A HIGH/MEDIUM
    tool invoked *inside* `AgentRegistry.get().run()` has no top-level n8n Wait node bound to
    it; a pending approval created inside the run would (i) be swallowed as a tool failure,
    (ii) block the HTTP handler, or (iii) silently expire (TTL 3600s, `approval.py:242`) while
    the run reports success — all unsafe. v1 rule: **agent steps may only perform
    content/analysis; any tool call above LOW is refused/deferred, never executed inline.**
    Concretely, for the duration of an agent step the runner enforces a "workflow-agent" mode
    in which the agent is permitted to call LOW-risk tools only; any MEDIUM/HIGH tool call the
    agent attempts is **not executed** and is surfaced as a structured signal back to the
    workflow runner ("I need a gated action: tool=X, arguments=Y"). The runner converts that
    signal into an `awaiting_approval` outcome: it calls `ApprovalGate.check()` for that tool
    at the *step* boundary (so the pending approval is bound to a real Wait node / resume-URL,
    not orphaned inside the run), persists `approval_id` + resume_url + the
    `execution_id`+`step_id`, and returns `status:"awaiting_approval"` from `callback/step`.
    The must-not-happen invariant, stated explicitly: **an inner MEDIUM/HIGH tool must never
    execute inline during an agent run, and the run must never report success while having
    silently no-op'd a side-effecting tool.** Enforcement point: `app/workflows/runner.py`
    constrains the toolset/risk ceiling passed to the agent run for workflow execution, and
    propagates (never swallows) any deferred-tool signal. (The minimal v1 implementation may
    realize "refused/deferred" as: the workflow-agent toolset is filtered to LOW-risk tools so
    the agent literally cannot invoke a non-LOW tool, and the agent's instruction frames the
    step as content/analysis only; any genuine real-world action must be authored as its own
    top-level step in a later increment.)

  - **O-3-AMEND-3 — Resolver preconditions: verify approval from Redis, never trust being
    called (resolves B-3).** The server-side resolver that executes an approved tool and
    resumes n8n MUST:
    1. **Fire ONLY from the authenticated, ownership-checked
       `/api/approvals/{id}/approve` path** (`approval_routes.py:152-155`, `require_auth` +
       `approval.user_id == caller`). It is an internal hook on that path keyed by
       `approval_id → (resume_url, execution_id, step_id)`, NOT an n8n callback and NOT a
       network-reachable endpoint.
    2. **Re-load the `PendingApproval` from Redis and assert `status == "approved"`** before
       executing anything — it must not execute on the basis of being invoked, a stored
       `approval_id`, or any webhook body. An absent/expired/`rejected` record → treat as
       reject/halt, never approve (R-2).
    3. **Re-classify the tool's risk server-side** (`classify_tool_risk`) and **take the tool
       name + arguments from the persisted PendingApproval / IR, NEVER from the n8n resume
       body.** The resume body is data for n8n only; it is not trusted for what to execute.
    4. **Bind execution to the stored `execution_id` + `step_id`** so a resume cannot be
       redirected to a different step/workflow, and confirm the approval's `user_id` matches
       the execution's owning user.
    5. **Run atomically with / synchronously inside the approve path** so verification happens
       while the approved record still exists (the approved-record TTL is **300s**,
       `approval.py:360`). A **late approval** (record already expired, or the n8n Wait node
       already timed out) MUST be handled as a no-op halt: the resolver does NOT execute the
       tool, records the step as `failed` ("approval expired / window elapsed"), and resumes
       the n8n failure path (or lets the Wait node time out) — it never executes a HIGH-risk
       action against a stale approval.
    6. **Validate the resume_url host/scheme against `N8N_BASE_URL`** before calling it
       (allowlist — C-7) so an approved result cannot be POSTed to an attacker host.

  **O-4 — n8n is a default docker-compose service AND the sole scheduler of record for
  workflows.** Add `n8nio/n8n` (pinned tag, named volume, healthcheck) to
  `founder-os/docker-compose.yml` as a default service so the local-first "one command" stack
  includes it (RISK-5: pinned + healthchecked + documented opt-out via compose profile if
  footprint is a concern). n8n owns ALL workflow triggering (cron via n8n Schedule nodes,
  manual via REST trigger); Founder OS does **not** add APScheduler jobs for workflows.
  APScheduler stays scoped to the existing weekly-planner job only. This makes n8n the single
  trigger of record and removes any double-fire surface (RISK-6); `Workflow.schedule_cron` is a
  mirror of the n8n Schedule node for display, with the n8n definition authoritative for
  execution. Deployment hardening (R-1): pin a version with known-good security defaults and do
  not expose the n8n editor publicly.

  **O-5 — Link-out to the n8n editor for v1 (no embed/SSO).** v1 surfaces a link to the n8n
  editor URL for a workflow (`{N8N_BASE_URL}/workflow/{n8n_workflow_id}`); embedded/SSO is
  explicitly deferred. Rationale: minimal, matches the product lean, keeps n8n "invisible by
  default, advanced affordance on demand", and avoids building an iframe/SSO bridge before the
  loop is proven. Founder OS remains the primary surface (list, run-now, history); the editor is
  the escape hatch for the rare edit.

- Conditions for execution (C-1..C-8 — the E1/F1 build checklist; verified on the diff by the
  second eng-security pass per CLAUDE.md §7):

  - **C-1 — Atomic single-use / replay.** Two concurrent fires of the same
    `(execution_id, step_id)` (n8n retry, duplicate cron, replay) MUST NOT both execute.
    Enforce with an atomic guard — a conditional `UPDATE … WHERE step is in a runnable state`
    (DB row-level, check rowcount) or a Redis `SET NX` lock keyed `(execution_id, step_id)` —
    never a read-then-write on the JSONB `step_state` map (TOCTOU can double-fire a side
    effect). The callback proceeds only if it won the transition; otherwise it returns the
    existing terminal state. (Stated in Contract 3.)
  - **C-2 — Execution binding.** On every `callback/step` and `callback/finish`, load the
    `WorkflowExecution`, assert `workflow_id == token.workflow_id` AND owning
    `user_id == token-derived user_id`, reject on mismatch (404/403, no detail leak). The
    `step_id` MUST exist in the persisted IR (authoritative step loaded by id, O-1) — never
    trust step content from the body.
  - **C-3 — Constant-time HMAC + canonical payload.** Use `hmac.compare_digest` (never `==`);
    deterministic canonicalization before signing/verifying (e.g.
    `json.dumps(payload, sort_keys=True, separators=(",",":"))`); verify the signature BEFORE
    trusting any payload field; reject a token whose decoded `workflow_id` ≠ the loaded
    workflow. Add an explicit test that a token minted for workflow A cannot verify against
    workflow B (the key derivation already prevents this).
  - **C-4 — `iat` bound + skew.** The 30-day `iat` window is acceptable ONLY because the token
    is additionally single-use-per-step (C-1) and execution-bound (C-2) — document that
    dependency. Reject `iat` in the future beyond ~60s skew and older than the bound. State
    plainly that single-use + execution-binding (NOT `iat`) is the real replay defense.
  - **C-5 — Secret-safe logging + error surface.** Never log `WORKFLOW_CALLBACK_SECRET`,
    `N8N_API_KEY`, the per-node token, or the n8n resume_url; never put any of these in an
    `HTTPException(detail=...)`; confirm no callback secret is ever stuffed into a
    `PendingApproval.description`/`arguments` (echoed to the founder via
    `/api/approvals/pending`); on HMAC failure return a fixed generic 401/403 (no enumeration
    oracle, no echo of the received token / which check failed). Enforce at `n8n_client.py`,
    `callback_auth.py`, `workflow_routes.py`, and the resolver.
  - **C-6 — Callback off Clerk AND off the dev bypass.** The callback router MUST depend on
    `require_workflow_callback` ONLY — never import/depend on `require_auth`/`optional_auth`
    (otherwise in `development` an `x-test-user` header would authenticate a callback and skip
    HMAC, per `app/auth.py:137-151`). `require_workflow_callback` MUST contain no
    `APP_ENV=="development"` shortcut — HMAC is verified in all environments. Test that the
    callback rejects (a) no token, (b) `x-test-user` with no token, (c) a Clerk Bearer JWT —
    the only accepted credential is a valid HMAC.
  - **C-7 — Resume-URL allowlist (SSRF).** Persist the resume_url only after the callback's
    HMAC + execution binding pass (C-2/C-3); before the resolver calls it, validate its
    host/scheme against `N8N_BASE_URL` (reject any origin that is not the known n8n instance);
    call it server-side only, never return it to a client, never log it (C-5).
  - **C-8 — IR validation integrity.** Risk is derived only via `classify_tool_risk(tool)`
    server-side; the validator MUST forbid any risk-like field in the IR, confirm
    `action.tool` ∈ ToolRegistry and `agent` ∈ registry slugs, reject `ir_version` it does not
    understand, and (per O-1-AMEND) reject non-LOW `action` tools. The callback MUST re-read
    the tool name from the persisted IR by `step_id` (never the body) — make this a tested
    assertion; it is what makes "an n8n edit cannot downgrade risk" actually true.

- Residual risks (accepted for v1, revisit in v2):
  - **R-1 — n8n compromise / readable n8n DB.** The per-node tokens live in n8n; anyone who
    can read its credential store gets long-lived (30-day `iat`) callback tokens for those
    workflows. Single-use-per-step (C-1) limits blast radius to not-yet-run steps. Hardening
    n8n's own auth/secrets is in scope for the O-4 deployment: pin a version with good security
    defaults; do not expose the n8n editor publicly.
  - **R-2 — Approval TTL vs cron latency.** `DEFAULT_PENDING_TTL = 3600` (`approval.py:242`);
    a workflow that parks on approval at 3am has its pending approval expire in 1h while the
    n8n Wait node may park far longer. Behavior is defined: timeout → mark failed, no silent
    proceed; the resolver treats an expired/absent approval as reject/halt, never approve
    (O-3-AMEND-3.5).
  - **R-3 — No rate-limiting on callback endpoints.** These are network-edge endpoints; a
    strong secret (B-4) makes HMAC brute-force infeasible, but v2 should add basic
    rate-limiting / fail-closed on repeated bad tokens.

- Consequences:
  - Reuse-first: `ApprovalGate` and `/api/approvals/*` are unchanged; `Workflow`/
    `WorkflowExecution` tables are reused; only one new column (`n8n_workflow_id`) plus a
    per-step status sidecar (in the existing `steps`/exec rows) are needed. The IR being the
    sole contract means n8n JSON is a compile artifact, never parsed back — the founder's n8n
    edits to cron/step-order round-trip because n8n is authoritative for *execution*, while
    Founder OS regeneration (v2+) is the authoritative source for *generation* (edit-vs-regen
    conflict is deferred — O-6, v2).
  - **v1 scope reduction forced by the amendments:** `action` steps are **LOW-risk-tool only**
    (O-1-AMEND); MEDIUM and HIGH real-world actions as *top-level `action` nodes* are **out of
    v1** (deferred to the v2 gated Wait-node path). `agent` steps run **content/analysis only**
    in no-side-effect mode (O-3-AMEND-2) — they may call LOW-risk tools but any MEDIUM/HIGH
    tool is deferred, never executed inline. The only `awaiting_approval` path exercisable in
    v1 is therefore an agent step deferring a gated action; the V1 "approve AND reject"
    verification should use that path (or, if the v2 top-level gated action is built early, a
    HIGH-risk top-level `action`). This keeps the hard safety metric (100% of HIGH-risk steps
    gated; zero un-gated externally-visible actions) provable for v1.
  - The pause/resume design (O-3) introduces a new server-side "execute the approved tool then
    resume n8n" path. This is the safety-critical surface; it must reuse `ApprovalGate` verbatim
    for the decision and only add the resume plumbing, and must satisfy O-3-AMEND-3.
  - HMAC callback auth (O-2) is the principal new attack surface and a hard eng-security gate.
    Rules out: trusting any identity from the request body; a single shared static callback
    token; unauthenticated webhooks; a blank/weak/defaulted callback secret (B-4).
  - n8n-as-default (O-4) grows the local footprint (one more container); mitigated by pinning,
    healthcheck, and a documented compose profile to disable it.
  - Out of scope (restated): webhook/event triggers (v2), embedded editor, branching/loops,
    multi-user workflows, workflow auto-evolution, replacing tool stubs; **MEDIUM/HIGH
    top-level `action` steps (v2 gated Wait-node path)**; agent-step real-world side effects.

- Links: [tasks/backlog/004-n8n-workflow-engine.md](../tasks/backlog/004-n8n-workflow-engine.md),
  `app/agents/approval.py` (check ~410-469, resolve ~340-372, TTLs ~242/360,
  classify ~159-170), `app/api/approval_routes.py` (approve ~135-172, ownership ~152-155),
  `app/models.py` (Workflow/WorkflowExecution ~233-296), `app/scheduler.py`,
  `founder-os/docker-compose.yml`, `app/config.py`. Related: ADR-001 (approval gate +
  provider neutrality are load-bearing invariants), ADR-006 (Alembic note: `versions/` is
  currently empty; schema applied via `schema.sql`).

## ADR-007 — One real user identity everywhere (no synthetic uuid5 keys)

- Date: 2026-06-11
- Status: accepted (shipped — task 008)
- Context: routes derived a synthetic `uuid5("clerk:<id>")` UUID never inserted into
  `users`; FK-constrained inserts (knowledge_items, tasks, …) 500'd for any user who
  hadn't onboarded, and reads/writes could disagree on the key. Verified live
  (`knowledge_items_user_id_fkey` violation; RAG stored nothing).
- Decision: all identity resolution goes through `app/users.py:get_or_create_user_id`
  (select → race-safe `INSERT … ON CONFLICT DO NOTHING` → select), creating a minimal
  users row on first sight (same semantics as onboarding). Applied across knowledge,
  agent, task-review, approval, activity routes and Celery agent tasks; activity event
  filtering keeps legacy uuid5 aliases so historical events still match.
- Consequences: RAG/tasks/approvals work pre-onboarding; one key for reads and writes;
  approvals created during agent runs are visible in the approval endpoints. Trade-off:
  helpers that lacked a db dependency open a short-lived session (acceptable; flagged
  for later consolidation).
- Links: [tasks/completed/008](../tasks/completed/008-prod-hardening-core.md), `app/users.py`.

## ADR-006 — Agent Evolution Engine: per-founder definition regeneration

- Date: 2026-06-11
- Status: accepted (shipped — task 003)
- Context: task 001 only *overlaid* per-founder `custom_instructions`; the founder wanted
  real evolution — agent *definitions* that differ per founder and regenerate as context
  grows. The global `agents` row is shared by all users, so per-founder definitions need
  separate, versioned storage applied at runtime.
- Decision: two new tables (`founder_context_models`, `agent_definitions`) — ORM +
  `schema.sql` DDL, **no Alembic** (the repo's `versions/` is empty; schema is managed
  via `schema.sql` + a one-time apply). A `FounderContextModelBuilder` distills
  `FounderProfile` + `UserProfileIntel` into a structured, hashed, versioned model
  (only re-versions on real change). An `AgentGenerator` regenerates each agent's full
  definition (system_prompt + decision_framework + selected_tools ⊆ the real tool menu)
  from (role spec + context model), staged `proposed`. Approval makes it `active` and
  supersedes the prior active row; `registry.get()` prefers the active per-user
  definition over the global `agents` row (base.py unchanged). Onboarding triggers it in
  the background (superseding task-001's overlay trigger; the specialize endpoints remain
  for manual tweaks).
- Consequences: genuine per-founder agents (proven against the live DB — registry serves
  the regenerated prompt). Approval-gated, versioned + reversible (rollback), bounded
  (N calls per context change). Trade-off: full behavior regeneration is sensitive →
  hard human-in-the-loop, never auto-activated. Out of scope (queued): continuous
  auto-evolution from memory/feedback (#4), dynamic NEW sub-agents (#3).
- Links: [tasks/completed/003](../tasks/completed/003-agent-evolution-engine.md),
  `app/agents/context_model.py`, `app/agents/generator.py`,
  `app/agents/registry.py` (`_load_active_definition`), `app/api/evolution_routes.py`.

## ADR-005 — Strategic systems-thinking prompt architecture

- Date: 2026-06-10
- Status: accepted (shipped — task 002)
- Context: the product agents ran as generic task executors; the founder wants
  founder-specific strategic systems-thinkers (Planner→CSO, Research→Market
  Intelligence, Product→Strategist/Architect, Content→Narrative Architecture,
  Ops→Operating-System Architect).
- Decision: a shared `app/agents/strategy.py` defines a `SYSTEMS_THINKING_PREAMBLE`
  (systems/incentives/constraints/feedback-loops/tradeoffs/first-principles + a
  5-point Decision Framework + an instruction to specialize to the injected founder
  context) and `strategic_header(role, charter)`. This is **prepended** to each
  agent's existing prompt — operations (tool protocols, calendar-intent rules, content
  formats) are preserved; strategy is layered on. Agents reference the founder context
  already injected by `base.py:340-480`.
- Consequences: low regression risk (operational instructions intact; e2e 50/50);
  one shared standard all agents follow; per-agent diff is a single prepend. Larger
  adaptation subsystems are designed in [agent-evolution.md](agent-evolution.md) and
  queued (tasks 003-006).
- Links: [tasks/completed/002](../tasks/completed/002-agent-strategic-prompt-upgrade.md),
  `app/agents/strategy.py`.

## ADR-004 — Code is the source of truth for agent definitions (synced to DB)

- Date: 2026-06-10
- Status: accepted (shipped — task 002)
- Context: rich agent prompts live in Python (`AGENT_CLASSES`), but runtime prefers
  the DB value (`base.py:351`), and the `agents` rows were seeded with **generic**
  prompts (schema.sql / migration). With no code→DB sync, the rich prompts were dead
  code — agents ran generic prompts (verified against the live DB).
- Decision: add `sync_agents_to_db` (registry.py), called at startup in the lifespan
  (`main.py`), which **upserts** each `AGENT_CLASSES` entry's prompt/capabilities/tools
  into its `agents` row. Code becomes the source of truth; the DB is a synced cache.
  `base.py:351` is left unchanged (DB still authoritative at runtime, so admin DB edits
  remain possible between deploys).
- Consequences: the rich/strategic prompts now actually run; idempotent; no schema
  migration. Trade-off: startup sync overwrites manual DB prompt edits — acceptable
  (manual prompt editing isn't a current workflow). Best-effort: a sync failure logs
  but does not block startup.
- Links: [tasks/completed/002](../tasks/completed/002-agent-strategic-prompt-upgrade.md),
  `app/agents/registry.py` (`sync_agents_to_db`), `app/main.py`.

## ADR-003 — Founder-aware agent specialization via `is_enabled` staging

- Date: 2026-06-10
- Status: accepted (shipped — task 001, 13/13 tests pass)
- Context: the product should ship agents specialized to each founder (the "Agent
  Evolution Engine" vision), but runtime per-user config application **already
  exists** (`registry.py:236`, `base.py:364`) and the MVP must avoid a schema
  migration and keep a human-approval guarantee.
- Decision: generate per-agent specialization from `FounderProfile` via one LLM call
  per active agent, and **stage proposals as `UserAgentConfig` rows with
  `is_enabled=False`** (invisible to the runtime loader, which filters
  `is_enabled == True`). Founder approval flips the row to `True`. Use explicit
  propose→approve **endpoints** as the gate rather than the tool `ApprovalGate`
  (which gates tool calls inside an agent run, not onboarding-time proposals).
- Consequences: no migration; reuses the existing apply path (verify-only);
  human-in-the-loop preserved. Trade-off: `is_enabled=False` overloads "proposed" and
  "user-disabled" — accepted for MVP; a dedicated `status` column is a later increment
  if the meanings need to diverge. Cost bounded to N active agents per profile change
  (explicitly **not** per task — the literal "redesign before every task" was rejected).
- Links: [tasks/active/001-founder-aware-agent-specialization.md](../tasks/active/001-founder-aware-agent-specialization.md).

## ADR-002 — Engineering meta-layer as the development "factory"

- Date: 2026-06-10
- Status: accepted
- Context: every session started cold and re-derived stack, conventions, and
  workflow; the founder repeatedly re-explained context.
- Decision: add a self-improving meta-layer (this `docs/`, `standards/`, `agents/`,
  `skills/`, `workflows/`, `meta/`, `tasks/`, `reports/`) governed by
  [CLAUDE.md](../CLAUDE.md), with engineering agents named distinctly (`eng-`) from
  the product's runtime agents.
- Consequences: durable context + repeatable workflows; small upkeep cost (keep
  docs in sync as the last workflow step). Adopted the blueprint vocabulary
  (executor/qa, product/security agents, state-folder tasks).
- Links: this whole meta-layer; [CLAUDE.md](../CLAUDE.md).

## ADR-001 — Pre-existing product architecture (baseline, recorded)

- Date: (pre-existing)
- Status: accepted
- Context: the product needs a multi-agent backend a solo founder can run locally.
- Decision: single Orchestrator (Stripe-Minions, agents-as-tools); FastAPI + async
  SQLAlchemy + Postgres/pgvector + Redis + Celery + APScheduler; Clerk JWT auth;
  3-tier approval gate; pluggable LLM provider with fallback (Ollama default);
  Next.js 16 dashboard. Details in [architecture.md](architecture.md).
- Consequences: OSS/local-first, no vendor lock-in; provider neutrality and the
  approval gate are load-bearing invariants. Recorded here as the baseline so future
  ADRs can reference and supersede specific choices.
- Links: [architecture.md](architecture.md), [vision.md](vision.md).
