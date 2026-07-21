# Workflow — New Feature

> The full mandatory process for building a feature in Founder OS — the 8 steps from
> [CLAUDE.md](../CLAUDE.md) §7. The shared artifact is a **task file** that moves
> through the [tasks/](../tasks/) state folders and that each stage appends to.
> **No code before an approved plan + architecture.**

## Stages & handoff contract

| Step | Stage | Agent | Consumes | Produces |
|---|-------|-------|----------|----------|
| 1 | Analyze + define | [eng-product](../.claude/agents/eng-product.md) | the founder's request | user stories, **acceptance criteria**, success metrics; roadmap priority; task in `tasks/backlog/` |
| 2 | Plan | [eng-planner](../.claude/agents/eng-planner.md) | the defined need | requirements breakdown, milestones, ordered task list; move task to `tasks/active/` |
| 3 | Architect | [eng-architect](../.claude/agents/eng-architect.md) | approved plan | **Architecture** section: data model + Alembic, API, file placement, integration points, risks; an ADR in [decisions.md](../docs/decisions.md) if significant |
| 4 | Execute | [eng-executor](../.claude/agents/eng-executor.md) | architecture | code + tests/verification; task → `review` |
| 5 | Review | [eng-reviewer](../.claude/agents/eng-reviewer.md) | the diff | findings list + verdict (approve / changes-requested) |
| 6 | QA | [eng-qa](../.claude/agents/eng-qa.md) | reviewed change | Pass/Fail per acceptance criterion (shown output) |
| 6a | Security | [eng-security](../.claude/agents/eng-security.md) | sensitive change* | security report + Pass/Fail |
| 7 | Document | executor / product | shipped change | update `docs/` + code comments as needed |
| 8 | Update roadmap | [eng-product](../.claude/agents/eng-product.md) | done change | move item to Shipped in [roadmap.md](../docs/roadmap.md); task → `tasks/completed/` |

\* **Security (6a) is mandatory** when the change touches auth, secrets, permissions,
the approval gate, or external input — see [standards/security.md](../standards/security.md).

Each stage is a fresh specialist session — invoke the matching native subagent
(`eng-product` … `eng-security`) or "Read `agents/<role>.md` and execute this stage."

## Quality gates (reject if…)

Per [CLAUDE.md](../CLAUDE.md): no tests · no documentation · no architecture rationale ·
excess complexity · duplicate functionality · security concerns. A gate failure
sends the task back to the responsible stage.

- **After Analyze** — acceptance criteria + success metrics exist and are testable.
- **After Plan** — user confirms scope before architecture.
- **After Architect** — user signs off on schema/API changes before execution.
- **After Review/QA/Security** — blockers loop back to the [executor](../.claude/agents/eng-executor.md) until clean.
- **Before done** — all acceptance criteria pass with shown output; docs + roadmap updated.

## Self-improvement (after the task)

Run the loop in [CLAUDE.md](../CLAUDE.md): what slowed us down? what knowledge was
missing? what should become a skill / agent / workflow? Capture it (a new skill, an
ADR, a roadmap item).

## Quick start

```
1. Read agents/product.md   → user stories + acceptance criteria for: <request>
2. Read agents/planner.md   → plan + task file in tasks/active/
3. Read agents/architect.md → architecture for tasks/active/<file>
4. Read agents/executor.md  → implement tasks/active/<file>
5. Read agents/reviewer.md  → review the diff
6. Read agents/qa.md        → validate vs acceptance criteria
   (+ agents/security.md if the change is sensitive)
7-8. Document + move task to completed/, update docs/roadmap.md
```
