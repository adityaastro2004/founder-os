# 012 — Phase 0: Foundation Revamp

- **Status:** completed (2026-07-03; CI green at HEAD `fba518f`: run 28673085612)
- **Opened:** 2026-07-03
- **Spec:** [docs/superpowers/specs/2026-07-03-phase0-foundation-revamp-design.md](../../docs/superpowers/specs/2026-07-03-phase0-foundation-revamp-design.md)
- **Plan:** [docs/superpowers/plans/2026-07-03-phase0-foundation-revamp.md](../../docs/superpowers/plans/2026-07-03-phase0-foundation-revamp.md)
- **Branch:** `phase0-foundation-revamp`

## Outcome

Everything verifiably working (audit report with PASS/FAIL + evidence; all FAILs
fixed with regression tests or deferred with task files) + integration adapter
framework, pytest harness, `turbo test`, CI unit tier.

## Gate record

- **eng-security (F2 diff): PASS**, no blockers; should-fixes S1–S5 all applied in
  `36bc612`. Residual observation (HIGH × always_deny → pending, pre-existing) →
  roadmap tech-debt.
- **eng-reviewer (full branch diff 00ae7e5..81e3825): REQUEST CHANGES → resolved**
  in `6e7e223`. Blocker B1 (stale `calendar_integration` import crashed
  `test_e2e_pipeline.py` — migration grep missed root scripts), S1 (same stale
  import in `test_system.py` token-copy path), S2 (adapter registration made
  idempotent), N1 (turbo.json formatting churn reverted), N2 (crawler test noted
  in testing.md), N3 (auto-generated docs/context.md committed). Everything else
  approved: rename proven content-identical, gate strictly strengthened, scope
  clean, tests genuinely pin their claims.
- **eng-qa: PASS — all 7 spec criteria met** (per-criterion evidence in its report,
  2026-07-03). Conditions: (1) push + confirm a green CI run at true HEAD before
  merge (prior green run 28654259024 was 6 commits behind); (2) close-out preamble
  wording corrected per its honesty flag. Live tier at close-out: **14 passed in
  6:30**; unit tier 27 passed; turbo test/lint/check-types green.

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
