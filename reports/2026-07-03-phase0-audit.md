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
| 7 | Google Calendar | | §7 |
| 8 | Workflows / automations (AOV + n8n) | | §8 |
| 9 | Approval gate | | §9 |
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

(filled by audit)

## §8 Workflows / automations

(filled by audit)

## §9 Approval gate

(filled by audit)

## §10 Remaining routers

(filled by audit)

## §11 Frontend

(filled by audit)

## Ranked fix list

(filled at end of Stage 1)
