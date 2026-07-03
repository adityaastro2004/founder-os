# 012 — Phase 0: Foundation Revamp

- **Status:** active
- **Opened:** 2026-07-03
- **Spec:** [docs/superpowers/specs/2026-07-03-phase0-foundation-revamp-design.md](../../docs/superpowers/specs/2026-07-03-phase0-foundation-revamp-design.md)
- **Plan:** [docs/superpowers/plans/2026-07-03-phase0-foundation-revamp.md](../../docs/superpowers/plans/2026-07-03-phase0-foundation-revamp.md)
- **Branch:** `phase0-foundation-revamp`

## Outcome

Everything verifiably working (audit report with PASS/FAIL + evidence; all FAILs
fixed with regression tests or deferred with task files) + integration adapter
framework, pytest harness, `turbo test`, CI unit tier.

## Acceptance criteria

Success criteria 1–7 of the spec, verbatim:

1. `./start.sh` boots the full stack cleanly from a fresh checkout; steps documented.
2. `reports/2026-07-03-phase0-audit.md` exists with a PASS/FAIL/BLOCKED verdict and
   real captured output for every subsystem listed in Stage 1.
3. Every FAIL is either fixed with a regression test or deferred as a
   `tasks/backlog/` file with a stated reason. Nothing silently dropped.
4. `pytest` runs the API test suite from `founder-os/apps/api/`; `turbo test` works
   at the monorepo root; CI runs the unit tier green.
5. `app/integrations/` adapter framework exists; Google Calendar is migrated onto it
   behavior-preservingly as the first adapter.
6. `docs/architecture.md` and `standards/testing.md` updated; a new ADR in
   `docs/decisions.md` records the integrations framework.
7. All work honestly reported per CLAUDE.md rule 7.
