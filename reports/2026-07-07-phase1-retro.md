# Phase 1 Retro — Company State Engine slice 1 (task 011)

> Constitution §9 self-improvement loop, run at close-out on 2026-07-07.

## What worked notably well

1. **Architecture-first paid off.** The eng-architect doc (10 questions, one
   decision each) meant zero mid-build design churn: every module was written
   against a § contract, and the reviewer could check fidelity mechanically.
2. **The live tier keeps catching what units can't.** All three real bugs this
   phase were *worker-process integration* failures invisible to 107 unit tests:
   - Celery worker registered **zero tasks** (pre-existing `autodiscover`
     misconfig — every queued agent run would have been rejected).
   - Sync-lock NX double-take deadlock (route's reservation vs task's re-take).
   - Worker mapper config missing the `users` FK import (API imported
     `app.models` via main.py; the worker chain didn't).
   Each now has a regression test that simulates the worker context.
3. **Phase 0's lessons compounded:** the F3 float8-cast went straight into the
   dedup SQL; the F1 "always queue" rule shaped §8; the S2 idempotent-register
   guard was reused for the obsidian adapter.

## What slowed development down

1. **Stale-read test harness bug** cost two 10-minute E2E timeouts before the
   real signal emerged: polling for a truthy report returns the *previous*
   sync's report instantly. Waits on async jobs must key on a monotonic marker
   (`last_synced_at` advancing), not presence. → Captured as a testing.md rule
   (see below).
2. **Background-vs-foreground process drift:** uvicorn hot-reloads code, the
   Celery worker does NOT — two E2E rounds ran against a stale worker until the
   restart became a habit. → testing.md rule.

## Knowledge captured (where it now lives)

- Worker-context regression tests (`tests/unit/test_celery_task_registration.py`)
  — the pattern for "imports that only break in the worker".
- `standards/testing.md` additions (this close-out): poll-for-advancement rule +
  "restart the worker after backend changes; uvicorn reload does not cover it".
- `tasks/backlog/014` — vault-read hardening (security S1) as a Phase 5 gate.

## Skill-promotion check (3rd-occurrence rule)

- **Live-audit runbook**: 2nd occurrence was Phase 0's audit; this phase's
  close-out sweep is close but not identical. Still at 2 — promote on the next
  "verify everything" request.
- **Subsystem build recipe** (architect §-contract → TDD tasks → live E2E →
  gates): 1st full occurrence; Notion (Phase 2) will be the 2nd — if it repeats
  cleanly, promote to `skills/build_integration.md` before Paperclip (Phase 4).

## Verification summary

(final numbers in the close-out section of task 011 / the PR body)
