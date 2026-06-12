# Workflow — Refactor

> Restructure code **without changing behavior**. Behavior-preserving at every step,
> with a safety net before the first edit. Uses the [refactor](../skills/refactor.md)
> and [optimize](../skills/optimize.md) skills.

## When to use

Reducing duplication, untangling a module, improving naming/structure, or a measured
performance pass — when the *observable behavior* should stay identical. If behavior
changes, it's a [new feature](new_feature.md); if it fixes a defect, it's a
[bug fix](bug_fix.md).

## Stages

| # | Stage | Skill / Agent | Produces |
|---|-------|---------------|----------|
| 1 | Characterize | [eng-qa](../agents/qa.md) / [skills/analyze.md](../skills/analyze.md) | a test or repeatable check capturing current behavior (add a thin one if missing) |
| 2 | Plan the change | [eng-architect](../agents/architect.md) | the target shape + the named smell; scope boundary |
| 3 | Refactor | [eng-executor](../agents/executor.md) via [skills/refactor.md](../skills/refactor.md) (or [optimize](../skills/optimize.md) for perf) | small behavior-preserving steps, check green after each |
| 4 | Verify equivalence | [eng-qa](../agents/qa.md) | same inputs → same outputs; the check still passes |
| 5 | Review | [eng-reviewer](../agents/reviewer.md) | confirm no behavior/security change, scope contained |

## Rules

- **Safety net first** — never refactor code that has no test/manual check; add one.
- **One concern at a time**; never mix behavior change with structure change.
- Keep the diff on-topic; don't reformat untouched code.
- Security model + provider neutrality intact ([standards/security.md](../standards/security.md)).
- For a perf refactor, [optimize](../skills/optimize.md) requires before/after numbers.
- Follow-ups the refactor reveals → a [tasks/](../tasks/) item or [roadmap](../docs/roadmap.md) tech-debt entry.

## Quick start

```
1. Read agents/qa.md / skills/analyze.md → capture current behavior with a check
2. Read agents/architect.md              → name the smell + target shape
3. Read agents/executor.md + skills/refactor.md → small steps, re-check each
4. Read agents/qa.md                      → confirm behavior unchanged
5. Read agents/reviewer.md               → review
```
