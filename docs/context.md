# Project context (auto)

Generated: 2026-07-19T16:38:28.808Z

## Detected stack

- GitHub Actions

## Git

- Branch: `feat/background-chat-runs`
- HEAD: `cd6286c`

## Recent commits

- `cd6286c` feat(chat): keep agent chats running across tab navigation _(Aditya Jain, 2026-07-18)_
- `5bdbc95` Merge pull request #12 from adityaastro2004/chore/deploy-env-sync _(Aditya Raj Jain, 2026-07-16)_
- `8a22668` ci(deploy): sync LLM provider keys from GitHub secrets into server .env _(Aditya Jain, 2026-07-16)_
- `e640b90` Merge pull request #10 from adityaastro2004/chore/postcss-override _(Aditya Raj Jain, 2026-07-14)_
- `99b0a68` Merge pull request #11 from adityaastro2004/schema-baseline-migration _(Aditya Raj Jain, 2026-07-14)_
- `1d08450` chore(security): override postcss to ^8.5.10 (closes final Dependabot alert) _(Aditya Jain, 2026-07-14)_
- `da6feaa` feat(db): 0000_baseline — alembic alone bootstraps a fresh DB (task 016, ADR-011) _(Aditya Jain, 2026-07-14)_
- `cb40e17` Merge pull request #8 from adityaastro2004/chore/security-dep-bumps _(Aditya Raj Jain, 2026-07-14)_
- `9313001` Merge pull request #9 from adityaastro2004/adityaastro2004-patch-1 _(Aditya Raj Jain, 2026-07-11)_
- `aa74575` add deployed link in readme _(Aditya Raj Jain, 2026-07-11)_
- `a581680` chore(security): dependency bumps for 78 Dependabot alerts _(Aditya Jain, 2026-07-11)_
- `b0e8ca3` Merge pull request #7 from adityaastro2004/phase2-notion-adapter _(Aditya Raj Jain, 2026-07-11)_
- `1e09320` ci(deploy): complete CD — SSM RunCommand via GitHub OIDC _(Aditya Jain, 2026-07-11)_
- `63e8253` fix(retrieval): embeddings honor EMBEDDING_* settings, decoupled from LLM_PROVIDER; knowledge_routes converged onto get_default_embedder _(Aditya Jain, 2026-07-11)_
- `b89bfbf` Merge pull request #6 from adityaastro2004/phase2-notion-adapter _(Aditya Raj Jain, 2026-07-11)_
- `c68dae6` fix(notion): eng-reviewer findings — B1 Settings crash on founder .env (+token echo), B2 containment relations, B3 conflict-path tombstone; S1 sorted incremental search+early-stop, S2 title pre-pass, S3 no cursor advance past errors, S4 typed transport retries, S5 latest-asserter tombstone guard (architect-line), S6 E2E hardening, S7 adapter composition tests, S8 recursive blocks; §3.5 strictness + nits _(Aditya Jain, 2026-07-11)_
- `97f34c9` test(notion): accept NOTION_ACCESS_TOKEN as env fallback for the live suite _(Aditya Jain, 2026-07-10)_
- `460b342` fix(notion): eng-security findings — S1 id pattern+canonical assert, S2 managed-chain exclusion + partial-ledger persistence, S3 walk-time pagination cap; nits: Retry-After clamp, prune verify-or-drop (+root-parent fix), title normalize, validate-then-upsert, conflict-path restore reactivation _(Aditya Jain, 2026-07-09)_
- `22e9899` test(notion): T8 live E2E — self-seeding workspace, pagination/safety/toggle/trash/token-hygiene flow; loud skip when unconfigured (a skip does NOT satisfy the task-015 gate) _(Aditya Jain, 2026-07-09)_
- `ffcffe1` feat(notion): T7 — adapter (cursor walk, tombstone diff, ledgered outbound), service D4, task D7, routes D6 (SecretStr token→integrations upsert, live validation), lifespan D9 _(Aditya Jain, 2026-07-09)_

## Inferred recent decisions

- `cd6286c` feat(chat): keep agent chats running across tab navigation
- `da6feaa` feat(db): 0000_baseline — alembic alone bootstraps a fresh DB (task 016, ADR-011)
- `63e8253` fix(retrieval): embeddings honor EMBEDDING_* settings, decoupled from LLM_PROVIDER; knowledge_routes converged onto get_default_embedder
- `c68dae6` fix(notion): eng-reviewer findings — B1 Settings crash on founder .env (+token echo), B2 containment relations, B3 conflict-path tombstone; S1 sorted incremental search+early-stop, S2 title pre-pass, S3 no cursor advance past errors, S4 typed transport retries, S5 latest-asserter tombstone guard (architect-line), S6 E2E hardening, S7 adapter composition tests, S8 recursive blocks; §3.5 strictness + nits
- `460b342` fix(notion): eng-security findings — S1 id pattern+canonical assert, S2 managed-chain exclusion + partial-ledger persistence, S3 walk-time pagination cap; nits: Retry-After clamp, prune verify-or-drop (+root-parent fix), title normalize, validate-then-upsert, conflict-path restore reactivation
- `ffcffe1` feat(notion): T7 — adapter (cursor walk, tombstone diff, ledgered outbound), service D4, task D7, routes D6 (SecretStr token→integrations upsert, live validation), lifespan D9

## Hotspots

- 11x — `reports/2026-07-03-phase0-audit.md`
- 9x — `docs/roadmap.md`
- 7x — `founder-os/apps/api/app/main.py`
- 6x — `docs/architecture.md`
- 6x — `founder-os/apps/api/app/api/state_routes.py`
- 6x — `founder-os/apps/api/app/config.py`
- 6x — `founder-os/apps/api/.env.example`
- 5x — `standards/testing.md`
- 5x — `founder-os/apps/api/requirements.txt`
- 5x — `founder-os/apps/api/app/state/reconciler.py`

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
.claude/worktrees/frontend-revamp-claude/
.claude/worktrees/heuristic-northcutt/
.turbo/
.turbo/cache/
.vscode/
.vscode/settings.json
CLAUDE.md
DEPLOY.md
docs/
docs/agent-evolution.md
docs/architecture.md
docs/context.md
docs/decisions.md
docs/requirements.md
docs/roadmap.md
docs/superpowers/
docs/superpowers/plans/
docs/superpowers/specs/
docs/vision.md
founder-os/
founder-os/.env.local
founder-os/.env.production.example
founder-os/.npmrc
founder-os/.turbo/
founder-os/.turbo/cache/
founder-os/.turbo/preferences/
founder-os/.vercel/
founder-os/.vercel/.env.production.local
founder-os/.vercel/README.txt
founder-os/.vercel/output/
founder-os/.vercel/project.json
founder-os/Caddyfile
founder-os/README.md
founder-os/apps/
founder-os/apps/api/
founder-os/apps/docs/
founder-os/apps/web/
founder-os/docker-compose.prod.yml
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
reports/2026-07-03-phase0-audit.md
reports/2026-07-03-phase0-retro.md
reports/2026-07-07-phase1-retro.md
reports/2026-07-14-task016-retro.md
reports/README.md
scripts/
scripts/deploy-server.sh
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
tasks/active/015-notion-adapter.md
tasks/active/017-agent-history-replay-fix-guardrails.md
tasks/backlog/
tasks/backlog/004-n8n-workflow-engine.md
tasks/backlog/004-workflow-execution-engine.md
tasks/backlog/005-temporal-memory-injection.md
tasks/backlog/006-reasoning-scaffolding.md
tasks/backlog/007-feedback-behavior-loop.md
tasks/backlog/013-planner-async-generation.md
tasks/backlog/014-vault-read-hardening.md
tasks/backlog/016-alembic-baseline.md
tasks/backlog/018-event-bus-user-scoping.md
tasks/completed/
tasks/completed/001-founder-aware-agent-specialization.md
tasks/completed/002-agent-strategic-prompt-upgrade.md
tasks/completed/003-agent-evolution-engine.md
tasks/completed/008-prod-hardening-core.md
tasks/completed/009-pdf-rag-goal-autofill.md
tasks/completed/010-knowledge-tab-file-upload.md
tasks/completed/011-company-state-engine.md
tasks/completed/012-phase0-foundation-revamp.md
tasks/completed/016-schema-baseline-migration.md
workflows/
workflows/bug_fix.md
workflows/new_feature.md
workflows/refactor.md
workflows/release.md
```
