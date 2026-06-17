# Project context (auto)

Generated: 2026-06-17T02:51:02.979Z

## Detected stack

- GitHub Actions

## Git

- Branch: `ci/github-actions`
- HEAD: `af2a110`

## Recent commits

- `af2a110` added other agents and pdf rag for knowledge _(Aditya Jain, 2026-06-12)_
- `b3caad9` chore: merge remote changes, keep .env.example template _(Aditya Jain, 2026-05-19)_
- `bb2912f` chore: remove tracked caches, logs, backups; add root .gitignore _(Aditya Jain, 2026-05-19)_
- `426cf06` Delete founder-os/apps/api/.env.example _(Aditya Raj Jain, 2026-05-19)_
- `c32f8be` Merge pull request #2 from adityaastro2004/copilot/vscode-mmx3hltc-x7lw _(Aditya Raj Jain, 2026-03-30)_
- `715714e` Merge branch 'main' into copilot/vscode-mmx3hltc-x7lw _(Aditya Raj Jain, 2026-03-30)_
- `8851db8` Add web crawler research module and API _(Aditya Jain, 2026-03-30)_
- `50eeb0f` Wire agent tools to DB, add web search & safety _(Aditya Jain, 2026-03-30)_
- `35cb7ac` Fix planner chat failing to push weekly plans to Google Calendar _(Aditya Jain, 2026-03-24)_
- `01ebc0c` Merge pull request #1 from adityaastro2004/claude/compassionate-nobel _(Aditya Raj Jain, 2026-03-24)_
- `43c8789` Fix security issues, add missing deps, and improve setup UX _(Aditya Jain, 2026-03-24)_
- `2e08e9b` Auto-push weekly plans to Google Calendar _(Aditya Jain, 2026-03-19)_
- `bf0f39f` update _(Aditya Jain, 2026-03-19)_
- `b6c9cae` log update _(Aditya Jain, 2026-03-19)_
- `c2bf276` Checkpoint from VS Code for cloud agent session _(Aditya Jain, 2026-03-19)_
- `baf504e` Add settings API, founder profile and agent fixes _(Aditya Jain, 2026-03-09)_
- `a798b59` api key update _(Aditya Jain, 2026-03-09)_
- `2743cc1` Add MMR retriever and session history _(Aditya Jain, 2026-03-09)_
- `9bdcb07` Add profile intelligence and social media batches _(Aditya Jain, 2026-03-09)_
- `6a81a68` Add agent chat, calendar delete options, tests _(Aditya Jain, 2026-03-08)_

## Inferred recent decisions

- `35cb7ac` Fix planner chat failing to push weekly plans to Google Calendar
- `43c8789` Fix security issues, add missing deps, and improve setup UX

## Hotspots

- 6x — `founder-os/logs/api.log`
- 5x — `founder-os/logs/celery.log`
- 5x — `founder-os/logs/web.log`
- 4x — `founder-os/apps/api/app/agents/registry.py`
- 4x — `founder-os/apps/api/.env.example`
- 4x — `founder-os/apps/api/app/config.py`
- 3x — `founder-os/apps/api/app/agents/agents.py`
- 3x — `founder-os/apps/api/app/agents/execution.py`
- 3x — `founder-os/apps/api/app/__pycache__/config.cpython-314.pyc`
- 3x — `founder-os/apps/api/app/agents/__pycache__/agents.cpython-314.pyc`

## Top-level tree

```
.claude/
.claude/agents/
.claude/agents/eng-architect.md
.claude/agents/eng-executor.md
.claude/agents/eng-planner.md
.claude/agents/eng-product.md
.claude/agents/eng-qa.md
.claude/agents/eng-reviewer.md
.claude/agents/eng-security.md
.claude/settings.json
.claude/settings.local.json
.claude/skills/
.claude/skills/analyze/
.claude/skills/debug/
.claude/skills/optimize/
.claude/skills/refactor/
.claude/skills/security_audit/
.claude/worktrees/
.claude/worktrees/compassionate-nobel/
.claude/worktrees/heuristic-northcutt/
.vscode/
.vscode/settings.json
AUDIT.md
CLAUDE.md
ONBOARDING.md
agents/
agents/architect.md
agents/executor.md
agents/planner.md
agents/product.md
agents/qa.md
agents/reviewer.md
agents/security.md
docs/
docs/agent-evolution.md
docs/architecture.md
docs/decisions.md
docs/requirements.md
docs/roadmap.md
docs/vision.md
founder-os/
founder-os/.npmrc
founder-os/.turbo/
founder-os/.turbo/cache/
founder-os/.turbo/preferences/
founder-os/README.md
founder-os/apps/
founder-os/apps/api/
founder-os/apps/docs/
founder-os/apps/web/
founder-os/docker-compose.yml
founder-os/logs/
founder-os/logs/api.log
founder-os/logs/celery.log
founder-os/logs/web.log
founder-os/package-lock.json
founder-os/package.json
founder-os/packages/
founder-os/packages/eslint-config/
founder-os/packages/typescript-config/
founder-os/packages/ui/
founder-os/start.sh
founder-os/turbo.json
meta/
meta/run-nightly-test-sweep.md
meta/scaffold-orchestration.md
meta/scaffold-skill.md
meta/scaffold-trio.md
readme.html
readme.md
reports/
reports/README.md
skills/
skills/analyze.md
skills/debug.md
skills/optimize.md
skills/refactor.md
skills/security_audit.md
standards/
standards/api.md
standards/coding.md
standards/security.md
standards/testing.md
standards/ux.md
tasks/
tasks/README.md
tasks/TEMPLATE.md
tasks/active/
tasks/backlog/
tasks/backlog/004-workflow-execution-engine.md
tasks/backlog/005-temporal-memory-injection.md
tasks/backlog/006-reasoning-scaffolding.md
tasks/backlog/007-feedback-behavior-loop.md
tasks/completed/
tasks/completed/001-founder-aware-agent-specialization.md
tasks/completed/002-agent-strategic-prompt-upgrade.md
tasks/completed/003-agent-evolution-engine.md
tasks/completed/008-prod-hardening-core.md
tasks/completed/009-pdf-rag-goal-autofill.md
tasks/completed/010-knowledge-tab-file-upload.md
workflows/
workflows/bug_fix.md
workflows/new_feature.md
workflows/refactor.md
workflows/release.md
```
