---
id: NNN
title: <short title>
status: backlog          # backlog | in-progress | blocked | review | done
stage: product           # product | planner | architect | executor | reviewer | qa | security
owner: eng-product       # the agent currently responsible
created: YYYY-MM-DD
dependencies: []          # task ids / external blockers
links: []                # related tasks, PRs, docs
---

# NNN — <title>

> Lives in `tasks/backlog/` → `tasks/active/` → `tasks/completed/` (move the file as
> state changes — the folder is authoritative).

## Objective
<One or two sentences: the intended outcome and why.>

## User stories  <!-- eng-product -->
- As a <user>, I want <capability> so that <value>.

## Acceptance criteria
- [ ] <testable criterion 1>
- [ ] <testable criterion 2>

## Success metrics  <!-- eng-product -->
- <how we'll know it worked>

## Out of scope
- <explicitly excluded>

## Requirements / open questions  <!-- eng-planner -->
- <breakdown, constraints, anything needing user sign-off>

---

## Architecture  <!-- eng-architect; add an ADR to docs/decisions.md if significant -->
- Data model + Alembic:
- API (endpoints, auth, shapes; registration in main.py):
- File placement / components reused:
- Integration points (agents, tools, memory, approval, celery):
- Risks / trade-offs:

## Build notes  <!-- eng-executor -->
- Changed files:
- How verified (test file / command / manual):

## Review findings  <!-- eng-reviewer -->
- [severity] file:line — issue → fix
- Verdict:

## QA results  <!-- eng-qa -->
- Command:
- Pass/Fail per acceptance criterion (with output):

## Security report  <!-- eng-security; required if change touches auth/secrets/approval/input -->
- [severity] file:line — risk → fix
- Verdict (Pass/Fail):
