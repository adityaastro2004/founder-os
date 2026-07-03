# 013 — Async / streaming interactive plan generation

- **Status:** backlog (deferred from Phase 0 audit, F1 — see
  [reports/2026-07-03-phase0-audit.md](../../reports/2026-07-03-phase0-audit.md) §6)
- **Opened:** 2026-07-03

## Symptom / evidence

Interactive plan generation (`POST /api/test/plan`, and the founder-facing planner
generate path) runs **two sequential LLM generations** (markdown plan → parse-to-JSON,
each `max_tokens=4096`). Measured **486s end-to-end** on the default local provider
(`ollama/llama3.1:8b`, MacBook Air) vs 15–30s on hosted APIs. Any sane HTTP client
timeout fails first on local-first defaults; the audit's F1 "timeout" was exactly this.

## Why deferred (not fixed in Phase 0)

The server path is *correct* — it completed with a valid plan (HTTP 200). Making
interactive generation pleasant on slow local providers is a design change, not a
minimal repair: enqueue via Celery (queues already exist) + status polling
(`/api/queue` pattern already exists) or SSE streaming, plus frontend affordances.
Phase 0 fixed the test-side defects instead (provider-aware timeout; payload actually
carrying the goals — `test_system.py` was sending fields Pydantic silently dropped).

## Acceptance criteria (when picked up)

1. Plan generation runs as a background job (Celery) with immediate job-id response.
2. Status/result pollable via the existing queue pattern; frontend shows progress.
3. Works on ollama default without any client timeout tuning.
4. Regression test at both tiers (unit: job enqueue/state machine; live: end-to-end).
