# reports/ — Run & Release Reports

Durable, auditable output from orchestrations and releases — the record of *what the
system did*, so an unattended or multi-stage run is reviewable after the fact.

## What lands here

- **Release reports** — from [workflows/release.md](../workflows/release.md):
  `release-<YYYY-MM-DD>-<slug>.md`. What shipped, the task(s), QA + security results,
  migration applied, **rollback plan**, follow-ups logged to the [roadmap](../docs/roadmap.md).
- **Orchestration run reports** — from runbooks like
  [meta/run-nightly-test-sweep.md](../meta/run-nightly-test-sweep.md):
  `sweep-<YYYY-MM-DD>.md` etc. (The nightly sweep's *triage* artifact is a
  `tasks/` file; a summary/run log can also land here.)
- **Self-improvement notes** — periodic "what slowed us down / what should become a
  skill or agent" retros (see [CLAUDE.md](../CLAUDE.md) self-improvement loop).

## Conventions

- Naming: `<kind>-<YYYY-MM-DD>-<slug>.md`.
- One report per run/release; never overwrite history — append a new dated file.
- Reports are **read-only history**: state facts and outcomes honestly, including
  failures. Link the task(s) and any PR.

> Distinct from `tasks/` (live work items that move through states) — `reports/` is
> the immutable log of completed runs.
