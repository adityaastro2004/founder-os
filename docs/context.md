# Project context (auto)

Generated: 2026-07-03T16:31:38.934Z

## Detected stack

- GitHub Actions

## Git

- Branch: `phase0-foundation-revamp`
- HEAD: `a410c9f`

## Recent commits

- `a410c9f` audit(phase0): close-out verification — all 7 spec criteria met; live tier 14/14 green _(Aditya Jain, 2026-07-03)_
- `4c9a958` test(phase0): RAG suite client timeout 60→300s — agent-chat section runs 30-90s+ on local ollama, flaked at 60s in soak (testing.md rule 5) _(Aditya Jain, 2026-07-03)_
- `01f3f40` test(phase0): RAG agent-grounding check FAIL→WARN — LLM content-quality assertion flaked in close-out soak, passed on immediate re-run (testing.md rule 4); retrieval stays hard-asserted structurally _(Aditya Jain, 2026-07-03)_
- `d0db615` chore(phase0): record security + review gate outcomes in task 012 _(Aditya Jain, 2026-07-03)_
- `6e7e223` fix(phase0): eng-reviewer findings — B1 stale calendar import in test_e2e_pipeline (crashed suite), S1 same in test_system token-copy path, S2 idempotent adapter registration, N1 turbo.json formatting, N2 crawler test noted in testing.md _(Aditya Jain, 2026-07-03)_
- `81e3825` docs(phase0): ADR-010, testing standard rewrite (3 tiers), architecture integrations+testing sections, roadmap phase table _(Aditya Jain, 2026-07-03)_
- `1f86319` ci(phase0): run pytest unit tier in backend job _(Aditya Jain, 2026-07-03)_
- `70018b5` chore(phase0): turbo test → API unit tier (apps/api joins npm workspace) _(Aditya Jain, 2026-07-03)_
- `1811ee3` refactor(phase0): calendar → integrations/google_calendar + first adapter (behavior-preserving) _(Aditya Jain, 2026-07-03)_
- `80c8c86` feat(phase0): integration adapter framework — base ABC + registry (ADR-010) _(Aditya Jain, 2026-07-03)_
- `597dc77` audit(phase0): record F1-F3 fix dispositions + eng-security PASS _(Aditya Jain, 2026-07-03)_
- `6de8d3a` fix(phase0): F3 hybrid search scored 0.0 — root cause: Postgres inferred float params as bigint in the RRF division, integer-dividing every score to 0 (ranking ties) _(Aditya Jain, 2026-07-03)_
- `36bc612` fix(phase0): F2 approval gate — explicit 'ask' preference now gates; root cause: unset was conflated with 'ask' so check() auto-approved both _(Aditya Jain, 2026-07-03)_
- `d0b5c6e` fix(phase0): F1 plan-generation timeout — root cause: two sequential 4k-token LLM calls take 486s on local ollama vs the test's fixed 300s cap _(Aditya Jain, 2026-07-03)_
- `5e85d79` test(phase0): pytest harness — unit/regression/live tiers, 13 scripts wrapped _(Aditya Jain, 2026-07-03)_
- `1fe9991` audit(phase0): complete — §10 §11 PASS; ranked fix list F1-F3 + founder items B1-B2 _(Aditya Jain, 2026-07-03)_
- `2c469f3` audit(phase0): §7 calendar (config PASS, push BLOCKED on OAuth) + §9 approval gate FAIL (F2: 'ask' pref no-op) _(Aditya Jain, 2026-07-03)_
- `ca04fa5` audit(phase0): §8 workflows — PASS (AOV + n8n suites green, n8n reachable) _(Aditya Jain, 2026-07-03)_
- `a18ac04` audit(phase0): §3 agent layer — PASS (live LLM round-trip verified) _(Aditya Jain, 2026-07-03)_
- `84eefaf` audit(phase0): core suites — §4 §5 PASS, §6 FAIL (plan-gen timeout F1) _(Aditya Jain, 2026-07-03)_

## Inferred recent decisions

- `6e7e223` fix(phase0): eng-reviewer findings — B1 stale calendar import in test_e2e_pipeline (crashed suite), S1 same in test_system token-copy path, S2 idempotent adapter registration, N1 turbo.json formatting, N2 crawler test noted in testing.md
- `81e3825` docs(phase0): ADR-010, testing standard rewrite (3 tiers), architecture integrations+testing sections, roadmap phase table
- `1811ee3` refactor(phase0): calendar → integrations/google_calendar + first adapter (behavior-preserving)
- `80c8c86` feat(phase0): integration adapter framework — base ABC + registry (ADR-010)
- `597dc77` audit(phase0): record F1-F3 fix dispositions + eng-security PASS
- `6de8d3a` fix(phase0): F3 hybrid search scored 0.0 — root cause: Postgres inferred float params as bigint in the RRF division, integer-dividing every score to 0 (ranking ties)
- `36bc612` fix(phase0): F2 approval gate — explicit 'ask' preference now gates; root cause: unset was conflated with 'ask' so check() auto-approved both
- `d0b5c6e` fix(phase0): F1 plan-generation timeout — root cause: two sequential 4k-token LLM calls take 486s on local ollama vs the test's fixed 300s cap
- `1fe9991` audit(phase0): complete — §10 §11 PASS; ranked fix list F1-F3 + founder items B1-B2

## Hotspots

- 10x — `reports/2026-07-03-phase0-audit.md`
- 4x — `docs/roadmap.md`
- 4x — `founder-os/apps/api/app/main.py`
- 4x — `founder-os/apps/api/.env.example`
- 3x — `founder-os/apps/api/test_rag_pipeline.py`
- 3x — `docs/context.md`
- 3x — `founder-os/apps/api/test_system.py`
- 3x — `standards/testing.md`
- 3x — `docs/architecture.md`
- 3x — `docs/decisions.md`

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
founder-os/.env.production.example
founder-os/.npmrc
founder-os/.turbo/
founder-os/.turbo/cache/
founder-os/.turbo/preferences/
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
tasks/active/012-phase0-foundation-revamp.md
tasks/backlog/
tasks/backlog/004-n8n-workflow-engine.md
tasks/backlog/004-workflow-execution-engine.md
tasks/backlog/005-temporal-memory-injection.md
tasks/backlog/006-reasoning-scaffolding.md
tasks/backlog/007-feedback-behavior-loop.md
tasks/backlog/011-company-state-engine.md
tasks/backlog/013-planner-async-generation.md
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
