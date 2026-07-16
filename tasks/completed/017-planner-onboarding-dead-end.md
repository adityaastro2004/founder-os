---
id: 017
title: Planner "Setup Required" dead end — bridge onboarding to planner profile
status: done
stage: qa
owner: eng-executor
created: 2026-07-16
dependencies: []
links: []
---

# 017 — Planner "Setup Required" dead end

## Objective
The Planner page showed a dead-end card — "Setup Required / No profile found.
Call POST /api/planner/onboard to get started." — with no way for the founder to
act on it from the UI.

## Root cause
Two disconnected onboarding stores:

- The `/onboarding` wizard saves a `FounderProfile` via `POST /api/onboarding/profile`
  (`app/models.py`, `founder_profiles` table).
- The Planner reads its own `planner_users` row (`app/user_store.py`) that only
  `POST /api/planner/onboard` created — and **nothing in the UI ever calls that
  endpoint**. So even fully onboarded founders hit a permanent "Setup Required"
  state showing a raw API instruction.

## Fix
- **Backend** (`apps/api/app/api/planner_routes.py`): `GET /api/planner/status`
  now auto-provisions the planner profile from the founder's existing
  `FounderProfile` when no `planner_users` row exists
  (`_bootstrap_from_onboarding` + pure mapper `_planner_profile_from_founder`).
  Onboarded founders land directly in the `pending_gcal` state, where the
  existing "Connect Google Calendar" flow takes over. The founder never re-enters
  context they already gave (constitution §0).
- **Frontend** (`apps/web/app/(dashboard)/dashboard/planner/page.tsx`): the
  `not_onboarded` card no longer shows the raw backend message; it shows friendly
  copy and a "Complete onboarding" link to `/onboarding` (safety net — normally
  the OnboardingGuard redirects un-onboarded users before they reach this page).

## Verification
- Regression test `apps/api/test_planner_onboarding_bridge.py` — 3/3 pass
  (full field mapping incl. Decimal MRR → float and working_hours → work-hours
  string; None-field defaults; partial working_hours).
- `import app.api.planner_routes` clean.
- `turbo check-types lint --filter=web` — 4/4 tasks pass.
- Not verified live end-to-end (requires running stack + a Clerk JWT).
