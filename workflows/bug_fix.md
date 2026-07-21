# Workflow — Bug Fix

> A lighter loop than [new_feature](new_feature.md) for fixing a defect. Lead with
> root-cause analysis, not a patch.

## Stages

| # | Stage | Skill / Agent | Produces |
|---|-------|---------------|----------|
| 1 | Diagnose | [skills/debug.md](../skills/debug.md) | a deterministic repro + proven root cause (evidence-backed) |
| 2 | Fix | [eng-executor](../.claude/agents/eng-executor.md) | the minimal change that addresses the root cause + a regression test |
| 3 | Verify | [eng-qa](../.claude/agents/eng-qa.md) | repro now passes; nothing else broke (output shown) |
| 4 | Review | [eng-reviewer](../.claude/agents/eng-reviewer.md) | confirm correctness, no security/scope regression |

For a tiny, obvious fix you may collapse 2–4, but **never skip the regression
test** — a bug worth fixing is worth a check that keeps it fixed.

## Rules

- Find the **root cause** before changing code (no symptom-masking).
- Add a regression test that fails before the fix and passes after.
- Keep the diff minimal; security model intact; honest reporting.
- Record the cause + fix + verification in a [tasks/](../tasks/) file if non-trivial.

## Quick start

```
1. Use skills/debug.md         → reproduce and root-cause: <failure>
2. Read agents/executor.md     → apply the minimal fix + regression test
3. Read agents/qa.md           → confirm repro passes, suite green
4. Read agents/reviewer.md     → review the fix
```
