# Phase 0 Audit — 2026-07-03

> Verdicts: PASS / FAIL / BLOCKED. Every verdict has captured output.
> Probe environment: local macOS (Darwin 25.5.0), Docker, Ollama `llama3.1:8b` +
> `nomic-embed-text`, `APP_ENV=development`, branch `phase0-foundation-revamp`.
> Spec: docs/superpowers/specs/2026-07-03-phase0-foundation-revamp-design.md

| # | Subsystem | Verdict | Evidence section |
|---|-----------|---------|------------------|
| 1 | Boot (Docker, Alembic, uvicorn, Celery, web) | **PASS** | §1 |
| 2 | Auth path (Clerk + dev bypass + test_routes gating) | **PASS** | §2 |
| 3 | Orchestrator + agent chat | **PASS** | §3 |
| 4 | Memory (4-layer + temporal KG) | **PASS** | §4 |
| 5 | Knowledge / RAG | **PASS** | §5 |
| 6 | Planner + weekly plan + APScheduler | **FAIL** (F1: plan generation timeout) | §6 |
| 7 | Google Calendar | **PASS (config) / BLOCKED (push — founder OAuth)** | §7 |
| 8 | Workflows / automations (AOV + n8n) | **PASS** | §8 |
| 9 | Approval gate | **FAIL** (F2: explicit "ask" pref is a no-op) | §9 |
| 10 | Remaining routers (crawler, billing, settings, activity, history, queue) | | §10 |
| 11 | Frontend | | §11 |

## §1 Boot

**Verdict: PASS.** `./start.sh` booted cleanly end-to-end (2026-07-03 ~14:29 local).

- start.sh: `✔ Ollama found` · `✔ nomic-embed-text model available` · `✔ Migrations applied` · `✔ API server running (PID 1757)` · `✔ Celery worker running (PID 1787)` · `✔ Web dev server running (PID 1877)`; n8n profile active.
- Health: `GET /api/health` → `{"healthy": true, "checks": {"api": "ok", "postgres": "ok", "redis": "ok"}}`
- Web: `GET http://localhost:3000` → `200`
- Containers: `postgres Up (healthy)`, `redis Up (healthy)`, `n8n Up (healthy)`
- Alembic: `alembic current` → `0001_workflow_engine (head)`
- Celery: `celery@Adityas-MacBook-Air-5.local ready.` (queues default,agents,orchestrator)

*Note (doc nit, not a failure):* the health endpoint is `/api/health`; the `/api` prefix
lives on the router in `app/api/routes.py:9`, not in `main.py`.

## §2 Auth path

**Verdict: PASS.** The dev bypass and dev test routes are both provably hard-gated.

- `app/auth.py:137-151` `_dev_test_user`: returns `None` when `settings.APP_ENV != "development"` **before** the `x-test-user` header is ever read.
- `app/main.py:105-107`: `test_router` mounted only inside `if settings.APP_ENV == "development":` (comment: "Dev-only test routes (no auth required)").
- Live behavior (dev): `GET /api/agents` without header → **401**; with `x-test-user: audit-user` → **200** (agents list returned).
- Deployment requirement carried to Phase 5: production must set `APP_ENV` ≠ `development`; both the bypass and `test_routes` then vanish.

*Observation for §3:* the agent registry lists `"model": "claude-sonnet-4-20250514"` on
agent definitions while `LLM_PROVIDER=ollama` — display/DB field vs. runtime provider;
checked under §3.

## §3 Orchestrator + agent chat

**Verdict: PASS.** All four agent suites green + live LLM round-trip verified.

- `test_agent_prompts.py` exit 0 — strategy markers, role elevation, code→DB prompt
  sync idempotent.
- `test_agent_specialization.py` exit 0 — generate/approve/reject/parse paths.
- `test_agent_evolution.py` exit 0 — regeneration, supersede, rollback, registry
  override + fallback.
- `pytest test_content_agent.py` — 25 passed in 0.50s.
- **Live probe:** `POST /api/agents/orchestrator/chat` (dev bypass) → real reply from
  `ollama/llama3.1:8b`; response carries `agent, reply, llm_provider, model,
  tokens_used, cost_usd, pending_approvals, tool_calls_made, …`. Structure asserted,
  not content quality.
- §2 observation resolved: DB `model` field on agent definitions is display metadata;
  runtime provider comes from `LLM_PROVIDER` (`llm_provider` in the live response
  confirmed ollama).

## §4 Memory

**Verdict: PASS.** `test_memory.py` → `=== ALL TESTS PASSED ===`, exit 0.
Temporal KG CRUD, page types, importance scoring, pin/unpin all verified live.

## §5 Knowledge / RAG

**Verdict: PASS.** `test_rag_pipeline.py` → all checks green, exit 0: ingest (text,
second doc, markdown file upload), stats (3 items, 3 embeddings), hybrid / semantic
(top 0.669) / full-text / MMR search (3 categories), category filter, agent-uses-RAG
grounding (found `$499`/`enterprise`/`per seat` indicators), list, embeddings present.

*Observation (not a FAIL):* "Hybrid relevance — Top result score=0.000" — hybrid
search returns rank-worthy results but the reported hybrid score is 0.0; semantic
score works (0.669). Possible scoring/display defect inside hybrid fusion — logged
as low-priority item in the ranked fix list (F4).

## §6 Planner + weekly plan + APScheduler

**Verdict: FAIL (F1).** From `test_system.py` (37/41 pass, exit non-zero):

```
5. LLM PLAN GENERATION (Gemini 2.5 Flash)
  Generating plan with Gemini (this takes 15-30 seconds)...
  [FAIL] Plan generation — timed out
```

Onboard + profile management PASSED; "Generate rejects without GCal" guard PASSED;
memory-aware plan SKIPped (depends on GCal connect → §7 BLOCKED). Token/profile
persistence PASSED. Root cause TBD in Task 9 — note the script banner says the plan
path targets **Gemini 2.5 Flash** specifically while `LLM_PROVIDER=ollama`; suspects:
hardcoded provider routing in the planner path, dead/quota GEMINI key, or timeout too
tight for the 3-tier fallback chain.

## §3a Core-suite evidence for the agent layer (completed in §3)

`test_system.py` §8: List agents PASS (7 agents), LLM chat PASS via `ollama/llama3.1:8b`.
`test_e2e_pipeline.py`: 50 PASS / 0 FAIL in 2.9s — full pipeline trace with mocked LLM
(memory recall → context → parse → GCal-would-push → replan → memory store).

## §7 Google Calendar

**Verdict: PASS (config + OAuth URL) / BLOCKED (live push — needs founder consent).**

- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` present in `.env`.
- OAuth URL generation (via `test_system.py` §4): PASS — well-formed
  `accounts.google.com/o/oauth2/v2/auth?client_id=219004168797-….apps.googleusercontent.com…`.
- "Generate rejects without GCal" guard: PASS.
- Live push / event CRUD / memory-aware plan: **BLOCKED** — no OAuth tokens in the
  dev DB. **Founder step:** open the dashboard → Planner → Connect Google Calendar
  (or `GET /api/planner/connect` and visit the returned URL), grant access, then
  re-run `python3 test_system.py` — sections 4/6/7 will exercise live push.
- gcal tool risk classification exists (`gcal_create_event` etc. → MEDIUM; reads → LOW).

## §8 Workflows / automations

**Verdict: PASS.** All five suites exit 0 against the live server:

- `test_workflow_ir.py` — 16 passed (IR persistence, get_step)
- `test_workflow_compiler.py` — 19 passed (cron → Schedule Trigger node, manual
  trigger, connections)
- `test_workflow_generator.py` — 16 passed (incl. empty-goal rejected before LLM)
- `test_workflow_routes.py` — 13/13 (create → run → run-record; no route collision)
- `test_n8n_client.py` — 15 passed (transport failure → N8nUnavailableError; API key
  never leaks into error messages)
- n8n container: `Up (healthy)`, `GET :5678` → 200.

*Scope note:* this validates the default in-process AOV path end-to-end plus n8n
client/compiler correctness and n8n reachability. A live push of a compiled workflow
INTO n8n (API key pairing etc.) is task 004 scope — already `later` on the roadmap,
unchanged by this audit.

## §9 Approval gate

**Verdict: FAIL (F2)** — structure sound, one real defect, zero test coverage.

What's sound (verified by code read + live probes):
- `ExecutionEngine._execute_tool_calls` runs `approval_gate.check()` before **every**
  tool call when `user_id` is set (`app/agents/execution.py:307-330`); held calls
  return `pending_approval` placeholders (field observed live in chat responses).
- `classify_tool_risk`: HIGH_RISK_TOOLS always → HIGH; unknown tools (e.g. MCP)
  default **MEDIUM**, not LOW (`app/agents/approval.py:159-170`).
- HIGH risk in `check()` → ALWAYS `_create_pending`, no bypass (`approval.py:419-429`).
- Live negative probe: content agent asked to "publish a tweet" had no such tool
  registered → no tool executed, nothing silently side-effected (LLM emitted JSON
  text only). `GET /api/approvals/pending` → `[]` (consistent: no tool call happened).

**F2 (defect):** `check()`'s docstring and the preference model say explicit
`pref == "ask"` → create pending approval; the implementation **auto-approves** on
`pref == "ask"` (`approval.py:456-461`). A founder who explicitly sets a tool to
"ask me first" is silently not asked — the human-in-the-loop override is a no-op for
LOW/MEDIUM tools. Correct semantics: unset preference → default policy
(LOW/MEDIUM auto-approve); explicit `"ask"` → pending approval.

**Coverage gap:** no `test_*.py` exercises `ApprovalGate`/`classify_tool_risk` at all
(grep over all 13 scripts: zero hits). Fix F2 with a proper unit suite.

*Note:* a live HIGH-risk hold cannot currently be tripped end-to-end because no
registered tool is in `HIGH_RISK_TOOLS` (they arrive with future integrations) —
enforcement verified at the `check()` level instead; unit tests to pin it.

## §10 Remaining routers

(filled by audit)

## §11 Frontend

(filled by audit)

## Ranked fix list

(filled at end of Stage 1)
