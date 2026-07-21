# Workflow — Release

> Ship verified work safely. The final gate before changes reach `main` / production.
> Report-honest, security-gated, and reversible.

## Preconditions (all must hold)

- The change went through [new_feature](new_feature.md) or [bug_fix](bug_fix.md) and
  its task is in `tasks/active/` at `status: review` with QA **passed** (output shown).
- A **[security](../.claude/agents/eng-security.md) Pass** for any change touching auth, secrets,
  permissions, the approval gate, or external input ([standards/security.md](../standards/security.md)).
- Schema changes have an Alembic migration; docs and [roadmap](../docs/roadmap.md) updated.

## Stages

| # | Stage | Owner | Produces |
|---|-------|-------|----------|
| 1 | Pre-flight | [eng-reviewer](../.claude/agents/eng-reviewer.md) | confirm quality gates pass; no unrelated churn in the diff |
| 2 | Security gate | [eng-security](../.claude/agents/eng-security.md) | Pass (a blocker here stops the release) |
| 3 | Verify build/tests | [eng-qa](../.claude/agents/eng-qa.md) | `turbo build`, `turbo lint`, `turbo check-types`, backend `test_*.py` all green (output shown) |
| 4 | Migrate | [eng-executor](../.claude/agents/eng-executor.md) | `alembic upgrade head` applied/validated where relevant |
| 5 | Publish | human-gated | branch + PR (or merge) — **only when the founder asks** |
| 6 | Completion report | [eng-product](../.claude/agents/eng-product.md) | report in [reports/](../reports/); move task to `tasks/completed/`; roadmap → Shipped |

## Hard rules

- **Never `git commit`/`push`/merge unless the founder explicitly asks** ([CLAUDE.md](../CLAUDE.md)).
- **Never release with an open security blocker** or failing build/tests.
- If on the default branch, branch first; commit message + PR body follow the repo
  conventions (Co-Authored-By trailer; Generated-with footer).
- Releases are **reversible** — note the rollback (revert PR / `alembic downgrade`) in
  the completion report.

## Completion report (reports/)

`reports/release-<YYYY-MM-DD>-<slug>.md`: what shipped, which task(s), QA + security
results, migration applied, rollback plan, and any follow-up/tech-debt logged to the
[roadmap](../docs/roadmap.md). See [reports/README.md](../reports/README.md).

## Quick start

```
1. Read agents/reviewer.md  → pre-flight quality gates
2. Read agents/security.md  → security gate (must Pass)
3. Read agents/qa.md        → turbo build/lint/check-types + test_*.py green
4. Read agents/executor.md  → apply/validate Alembic migration
5. (founder asks) branch + PR
6. Read agents/product.md   → write reports/ entry, move task to completed/, update roadmap
```
