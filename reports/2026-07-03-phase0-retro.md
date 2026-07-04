# Phase 0 Retro — Foundation Revamp (task 012)

> Constitution §9 self-improvement loop, run at close-out on 2026-07-03.

## What slowed development down

1. **uvicorn `--reload` vs. long live probes.** Any edit to a watched `.py` file
   under `apps/api` restarts the server and kills in-flight requests — which
   matters when a single plan-generation request runs ~8 minutes on local Ollama.
   Cost us one re-sequencing of the whole repair stage (batch all code edits, run
   live verification once at the end).
2. **Local-model latency invisible to tests.** The suite hardcoded hosted-API
   expectations ("15–30 seconds", 300s timeout) while the default provider is
   local-first Ollama at ~486s for the plan pipeline. The F1 "bug" was really a
   provider-blind test.
3. **Shell state resets between tool calls** (venv activation, cwd) caused a few
   dead commands — trivial each time, but worth the habit: absolute paths +
   re-activate per call.

## Knowledge that was missing (and where it now lives)

- **How the auth bypass works for local testing** (`x-test-user`, hard-gated on
  `APP_ENV=development`) → now documented in [standards/testing.md](../standards/testing.md)
  and audit report §2.
- **The RRF/bigint parameter-inference trap** (Postgres infers float params as
  bigint inside integer arithmetic → silent integer division) → pinned by a
  regression test and a load-bearing SQL comment in `vector_store.py` (F3).
- **Unset-vs-explicit preference semantics in the approval gate** → docstrings,
  ADR-scale comments, and a full 3-tier × preference test matrix (F2).
- **Provider-aware timeout discipline** → [standards/testing.md](../standards/testing.md)
  rule 5.

## What should become a skill / workflow / agent

- **Live-audit runbook (2nd occurrence trigger):** this audit's probe sequence
  (boot → auth → suites → routers → frontend, PASS/FAIL/BLOCKED with evidence) is
  reusable verbatim for any "is everything working?" request. If it happens once
  more, promote to `skills/live_audit.md` per the 3rd-occurrence rule — the audit
  report structure in [reports/2026-07-03-phase0-audit.md](2026-07-03-phase0-audit.md)
  is the template.
- **Workflow note added to bug_fix:** batch code edits before long live probes
  when uvicorn --reload is running (captured here; fold into
  `workflows/bug_fix.md` if it bites again).

## Artifacts produced

- ADR-010 (integration adapter framework) in [docs/decisions.md](../docs/decisions.md)
- Rewritten [standards/testing.md](../standards/testing.md) (3-tier contract)
- `tasks/backlog/013` (async plan generation) + roadmap tech-debt entries
  (HIGH × always_deny UX)
- This retro + the full audit report as the durable "state of the system" record.

## Verification summary

Cold restart → `pytest -q` 27 passed · `pytest -m live -q` **14 passed (6:30)** ·
`turbo test`/`lint`/`check-types` green · CI run 28654259024 success. Full outputs:
[audit report](2026-07-03-phase0-audit.md) → "Close-out verification". Two test
flakes surfaced during the soaks (LLM-content assert; provider-blind 60s timeout) —
both fixed per the new testing standard's own rules 4 and 5, which is the standard
proving its worth on day one.
