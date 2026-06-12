# tasks/ — Work Tracking

The shared artifact for the [new_feature](../workflows/new_feature.md),
[bug_fix](../workflows/bug_fix.md), and [refactor](../workflows/refactor.md)
workflows. One file per unit of work; every engineering agent reads and appends to it.

## State = folder (a task lives in exactly one)

```
tasks/
├── backlog/      # BACKLOG  — defined, not started
├── active/       # ACTIVE / BLOCKED / REVIEW — being worked (fine-grained via `status:`)
└── completed/    # DONE     — verified, all acceptance criteria pass
```

**The folder is authoritative** — a task exists in exactly one state. **Move** the
file between folders as it progresses (don't copy). Within `active/`, the `status:`
frontmatter distinguishes `in-progress` / `blocked` / `review`.

| State | Location | Owner |
|-------|----------|-------|
| BACKLOG | `backlog/` | [product](../agents/product.md) → [planner](../agents/planner.md) |
| ACTIVE | `active/` (`status: in-progress`) | [architect](../agents/architect.md) / [executor](../agents/executor.md) |
| BLOCKED | `active/` (`status: blocked`, note why) | whoever is blocked |
| REVIEW | `active/` (`status: review`) | [reviewer](../agents/reviewer.md) / [qa](../agents/qa.md) / [security](../agents/security.md) |
| DONE | `completed/` (`status: done`) | [product](../agents/product.md) updates [roadmap](../docs/roadmap.md) |

## Naming

`NNN-short-slug.md` — zero-padded incrementing number + kebab-case slug.
Examples: `001-add-tags-to-tasks.md`, `002-fix-jwks-cache-race.md`.

## Required fields (every task)

Objective · Owner agent · Dependencies · Acceptance criteria · Status. Use
[TEMPLATE.md](TEMPLATE.md).

## Creating a task

Copy [TEMPLATE.md](TEMPLATE.md) to `backlog/NNN-slug.md` and fill it in. The
[product](../agents/product.md) agent owns objective/criteria/metrics; the
[planner](../agents/planner.md) adds the breakdown and moves it to `active/`; later
stages append their sections and move it to `completed/` when done.

> Task files are durable project history — keep them honest and up to date.
