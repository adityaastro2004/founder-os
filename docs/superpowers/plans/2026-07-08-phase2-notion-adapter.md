# Phase 2 Notion Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Notion as the second observed source: token-authed API observation (pages + databases) → the existing reconciler → the unified model rendered back as a ledger-jailed "Founder OS" page tree in Notion.

**Architecture:** ALL decisions fixed in
[docs/superpowers/specs/2026-07-07-phase2-notion-adapter-architecture.md](../specs/2026-07-07-phase2-notion-adapter-architecture.md)
(§-references below). Implement without redesign; the ONLY engine changes are contract
deltas **D1–D9** (§7) — anything else engine-side is a deviation to flag, not make.
Product contract: [tasks/active/015-notion-adapter.md](../../../tasks/active/015-notion-adapter.md).

**Tech Stack:** httpx (no new deps) + pinned Notion-Version; httpx.MockTransport unit tier with checked-in fixture JSON; existing reconciler/renderer/Celery/lock machinery.

## Global Constraints

- Branch `phase2-notion-adapter`; backend cwd `founder-os/apps/api`; TDD per task; worker restart before any live run (testing.md rule 7); commits end with the Claude trailer.
- Token: `integrations` table only, `SecretStr` in requests, never in `state_sources.config`/logs/responses/task args (§2).
- Zero Alembic migration (§1 — verified; any deviation stops the work).
- Out-of-scope guardrails §12 binding. eng-security reviews the token path + the no-ApprovalGate-on-outbound decision (§8.4) after T7.

---

### T1: Foundations — settings, SyncResult.data (D5), obsidian signature (D8), credentials helper
Files: `app/config.py` (§11 six settings), `app/integrations/base.py` (D5 additive `data` field), `app/integrations/obsidian/adapter.py` (D8 widen `observe_source` signature, ignore extras), `app/integrations/credentials.py` (§2.2 `resolve_source_credentials` + `CredentialsMissing`), extend `tests/unit/test_integration_registry.py` (SyncResult.data default) + obsidian adapter test still green.
- [ ] Failing test → implement → `pytest -q` green → commit.

### T2: Notion client — transport only (§3.2)
Files: `app/integrations/notion/{__init__,client}.py`; test `tests/unit/test_notion_client.py` (MockTransport: pagination next_cursor@100, 429 Retry-After then success, exponential fallback, max-retries raise, 401→NotionAuthError with token-free message, min-interval pacing with injected clock, pinned Notion-Version on every request). Typed errors; counters api_requests/rate_limit_waits.
- [ ] Failing tests → implement → green → commit.

### T3: Mapper part 1 — objects→events (§3.4–3.7)
Files: `app/integrations/notion/mapper.py`; fixtures `tests/fixtures/notion_workspace/*.json` (§10.1 set); tests `test_notion_mapper.py` + `test_notion_external_id.py`. Emission order: goal/project/decision before note/task (Obsidian S1 lesson). Payloads content-only (hash stability pin), `observed_at=last_edited_time`, `attributes.status_property` audit field.
- [ ] Failing tests → implement → green → commit.

### T4: Mapper part 2 — md→blocks, hash-skip, tombstone diff (§3.6, §5)
Files: `mapper.py` (md→blocks over the renderer dialect ONLY, 100-block batching, 2000-char splitting, static-footer swap, `should_write(ledger, key, md)`; tombstone classification + reactivation predicate); tests `test_notion_blocks.py`, `test_notion_tombstone_diff.py`.
- [ ] Failing tests → implement → green → commit.

### T5: Ledger jail — the P0 (§4)
Files: `client.py` write sinks (`write_managed_page`/`archive_managed_page`/`replace_page_blocks` through `_jail`; `ManagedTreeViolation`); test `test_notion_managed_jail.py` (§4 battery incl. zero-mutations-outside-ledger∪root request-log assert, founder-moved→recreate, prune archives ledger orphans only).
- [ ] Failing battery → implement → green → commit.

### T6: Engine deltas D1–D3
Files: `app/state/reconciler.py` (D1 tombstone branch: trail-only resolution, is_active=False, archived counter, mirror purge, gated-never-created no-op §13, reactivation on newer observed_at), `app/state/dedup.py` (D2 `merge(..., hard_match=False)` retitle), `app/state/mirror.py` (D3 suffix rule + `purge_mirror(external_id)`), reconciler hard-path passes hard_match=True. Tests: extend `test_state_dedup.py` (retitle vs alias table), `test_state_reconciler_logic.py` (tombstone no-op predicate), mirror suffix unit.
- [ ] Failing tests → implement → `pytest -q` ALL green (Phase 1 suites must not regress) → commit.

### T7: Adapter + service/task/routes wiring (D4, D6, D7, D9; §3.1, §6, §8)
Files: `app/integrations/notion/adapter.py` (observe_source full/incremental per §6 pseudo, returns (events, cursor); sync with ledger via SyncResult.data; non-network check_source §8.2; idempotent register), `app/state/service.py` (D4), `app/tasks/state_tasks.py` (D7 TTL 1800 + full_walk), `app/api/state_routes.py` (D6: NotionConfig SecretStr token pop→integrations upsert→live validation 422s; type Literal; per-type dispatch; full_walk), `app/main.py` (D9). Tests: extend `test_state_routes_models.py` (NotionConfig 422 shapes, token absent from SourceResponse, Literal both), adapter unit vs fixtures.
- [ ] Failing tests → implement → green; live smoke: register Notion source 422-on-bad-token path with MockTransport-less real call? (skip if no token — smoke deferred to E2E). Commit. → **eng-security gate** (token path + §8.4 posture).

### T8: Live E2E (§10.2) — REQUIRES founder env
Files: `tests/live/test_state_notion_live.py` (skipif env missing with the loud gate-rule reason; seed step idempotent incl. ~105 bulk filler pages; flow steps 1–8 verbatim incl. safety snapshot via last_edited_time, churn-free, toggle-same-entity, trash→full_walk→archived, token hygiene log scan), `.env.example` (NOTION_TEST_TOKEN/NOTION_TEST_ROOT_PAGE_ID comment). **Founder supplies token + shared root page; a skip does NOT satisfy the task-015 gate.**
- [ ] Worker restart → run with env set → green → commit with the report artifact pasted into task 015.

### T9: Gates + close-out
- [ ] Full `pytest -q` + `pytest -m live -q` (all suites incl. Obsidian E2E — D2/D4 regress-check) + turbo sweep.
- [ ] eng-reviewer (fidelity vs D1–D9 + §s), fix findings; eng-qa vs task 015 AC/metrics.
- [ ] Docs (§11 docs step), retro (+ skill-promotion decision: 2nd clean recipe run → write `skills/build_integration.md`), task 015 → completed, roadmap Phase 2 done / Phase 3 next, memory, push, CI, PR.

## Self-review
- Every task maps to architecture §s; D1–D9 all covered (D1-D3→T6, D4/D6/D7/D9→T7, D5/D8→T1); AC coverage: mapping (T3), idempotency (T3 hash pins + E2E), jail P0 (T5+E2E snapshot), token hygiene (T7+E2E), pagination/rate limits (T2+E2E), archival (T4/T6+E2E), churn-free (T4+E2E), provenance (existing routes + E2E). No placeholders; § refs carry exact rules.
