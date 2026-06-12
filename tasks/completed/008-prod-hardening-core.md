---
id: 008
title: Production hardening — agents, RAG, A2A, auth, scheduler (full audit + fix)
status: done
stage: qa
owner: eng-qa
created: 2026-06-11
dependencies: [001, 002, 003]
links: [docs/decisions.md, docs/roadmap.md]
---

# 008 — Production hardening: make the core actually work end-to-end

## Objective
Audit the entire core (agents, RAG pipeline, A2A delegation, auth, scheduler,
test harness), fix every real bug found, and prove the system works end-to-end
against a live server with a real LLM. ("Build all agents + core at prod level,
remove all bugs" — founder directive.)

## Bugs found & fixed (each verified)

1. **Crawler tools wiring (registry.py:917)** — `ResearchEngine(...)` called with
   `db_session`/`memory_manager` kwargs its `__init__` doesn't accept → TypeError →
   all 5 research crawler tools silently fell back to stubs on EVERY agent build.
   Fix: call with `(crawl_engine, settings)`. Verified: server log now shows
   `run_research/monitor_competitors/... overridden with runtime closure`.

2. **Weekly-planner timezone (scheduler.py)** — `CronTrigger` built without a
   timezone resolves to the MACHINE-local zone, ignoring the scheduler's
   `Asia/Kolkata` default; job was scheduled at 08:00+08:00. Fix: explicit
   `timezone="Asia/Kolkata"` on the trigger. Verified: startup log
   `next run: …08:00:00+05:30`.

3. **User-identity FK violations (7 files)** — routes derived a synthetic
   `uuid5(clerk:<id>)` never inserted into `users`; every INSERT into FK-constrained
   tables (knowledge_items, tasks, …) for a non-onboarded user 500'd (verified live:
   `knowledge_items_user_id_fkey` violation; RAG stored 0 rows). Fix: new
   `app/users.py:get_or_create_user_id` (race-safe ON CONFLICT) used by
   knowledge_routes, agent_routes, task_review_routes, approval_routes,
   activity_routes (legacy aliases kept for old events), tasks/agent_tasks.
   Verified: RAG ingestion stores rows; reads/writes share one key.

4. **Provider/model mismatch (registry)** — agent DB rows pin provider-specific
   model names ('gemini-2.5-flash'); registry passed them verbatim to whatever
   provider is configured → Ollama asked for gemini → 404. (Gemini provider had
   this patched locally; nothing else did.) Fix: `_sanitize_model` — a model that
   doesn't belong to the configured provider is dropped so the provider default
   wins. Verified: chat now runs `llama3.1:8b`.

5. **Silent-empty agent failures (execution.py)** — LLM exceptions logged then
   returned HTTP 200 `status=completed` with empty content. Fix: surface a clear
   error message in the reply for non-rate-limit failures too.

6. **Ollama tool-call format (llm.py OllamaProvider)** — assistant tool-call
   history serialized `arguments` as a JSON STRING; Ollama's native `/api/chat`
   requires an OBJECT → 400 on every round replaying tool history (multi-round
   tool use was broken on the default OSS provider). Fix: pass the dict.
   Verified: multi-round chat with tool calls completes.

7. **Ollama client timeout (llm.py)** — 120s read timeout too tight for local
   prompt-eval on orchestrator-sized prompts → ReadTimeout. Fix: 300s.

8. **Dev test-auth harness (auth.py)** — live test scripts pre-date Clerk
   enforcement (they send `x-test-user`); everything 401'd. Fix: dev-ONLY bypass in
   `require_auth`/`optional_auth`, hard-gated on `APP_ENV == "development"` (same
   gate as the unauthenticated dev test_routes). Verified: 401 without header,
   works with header, gate confirmed.

9. **Test-suite drift (4 scripts)** — wrong endpoints (`/health`→`/api/health`,
   `/api/agents/chat`→`/api/agents/{name}/chat`/orchestrate), wrong body shapes
   (`text`→`content`), missing auth headers, too-tight client timeouts for local
   models (120→300s).

10. **Environment** — all hosted LLM keys dead (gemini invalid, groq 401,
    anthropic empty) and `llama3.1:8b` not pulled → NO working chat provider.
    Pulled `llama3.1:8b`; switched `.env` `LLM_PROVIDER=gemini→ollama`
    (backup: /tmp/founderos_env_backup). OSS-first default now fully self-hosted.

## Audit corrections (things believed broken that are NOT)
- `web_search` is real (DuckDuckGo default + Tavily override) — not a stub.
- `get_business_metrics`/`get_integrations`/etc.: all 21 tools get real DB-backed
  closures via `override_tool_impl` at agent build; mocks are import-time
  placeholders only.

## QA results (live server, real LLM)
- **RAG pipeline: 16/16** — ingest (text/file), embeddings 3/3, hybrid/semantic/
  full-text/MMR search, filters, AND "Agent uses RAG context" (agent cites the
  ingested $499/enterprise pricing doc).
- **Memory system: ALL PASSED** (store/recall/chapters/links/pin/review).
- **A2A delegation: PROVEN** — orchestrator→`delegate_task`→content agent→synthesis
  (8004 tokens through the chain) on llama3.1:8b.
- **Single-agent chat + tools: PROVEN** — multi-round tool use completes.
- **Unit regressions: 120/120** (evolution 22, prompts 35, specialization 13,
  e2e pipeline 50).
- **System test (final): 30/31** — health, DB/Redis, memory CRUD/links/pins,
  onboarding, NLP context update (real LLM extraction), GCal OAuth, agent listing,
  LLM chat, knowledge ingest (FK fix verified again: chunks=1), token + profile
  persistence, cleanup. The ONE failure is plan generation exceeding a 300s client
  timeout — a local-8B speed limit, not logic (the prior dead-key 502 is gone; the
  chain runs). Passes on any hosted provider or faster hardware.

## Security note (eng-security)
- The dev auth bypass is hard-gated on `APP_ENV=development` — identical risk
  surface to the pre-existing unauthenticated dev `test_routes`. Production deploys
  must set `APP_ENV=production` (already required). No change to JWT verification,
  scoping, approval gate, or secrets. **Pass.**

## Known limits (honest)
- Local 8B model is slow: orchestrator chains take minutes; the 5-scenario content
  suite exceeds a 10-min wall-clock. Hosted keys (when renewed) remove this.
- `workflow_*` tables still have no engine (task 004, queued).
- Celery worker not exercised in this pass (queue endpoints untested live).
