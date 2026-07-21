# Phase 1 State Engine (Slice 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Company State Engine core (4 tables, reconciler with write-gate + dedup) and the Obsidian adapter end-to-end: vault → canonical state + RAG → managed `FounderOS/` folder rendered back.

**Architecture:** ALL design decisions are fixed in
[docs/superpowers/specs/2026-07-04-phase1-state-engine-architecture.md](../specs/2026-07-04-phase1-state-engine-architecture.md)
(§-references below are to that doc). The executor implements it **without redesign**;
any needed design change is flagged, not improvised. Product criteria:
[tasks/completed/011-company-state-engine.md](../../../tasks/completed/011-company-state-engine.md).

**Tech Stack:** Python 3.14 / FastAPI / SQLAlchemy 2.0 async / Alembic / pgvector / Celery / Redis; `python-frontmatter` (new dep); pytest 3-tier harness from Phase 0.

## Global Constraints

- Branch `phase1-state-engine`; backend cwd `founder-os/apps/api` (venv per call).
- TDD per task: failing test → minimal impl → green → commit. Unit tier stays service-free.
- Schema via Alembic only (`0002_state_engine`, down_revision `0001_workflow_engine`).
- All routes `require_auth` + `get_or_create_user_id` scoping; reconciler is the ONLY entity writer; `client.write_managed` is the ONLY vault writer.
- Out-of-scope guardrails: architecture §10 is binding.
- eng-security gate after Task 11 (new authed routes + filesystem writes). eng-reviewer + eng-qa at close-out (Task 13).
- Commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Dependencies, config, ORM, migration
**Files:** Modify `requirements.txt` (`python-frontmatter>=1.1.0`), `app/config.py` (5 settings, §11), `app/main.py` (model import), `alembic/env.py` (model import). Create `app/state/__init__.py`, `app/state/models.py` (§1.2–1.6 exactly: `StateSource`, `CompanyStateEntity`, `StateObservation`, `StateRelation` — copy the `_ts_now()` idiom), `alembic/versions/0002_state_engine.py` (§1.7: create order sources → entities → observations → relations; `_has_table` guards; downgrade drops reverse). Test `tests/unit/test_state_models.py`.
- [ ] Failing test: `Base.metadata.tables` contains the 4 table names after `import app.state.models`; `CompanyStateEntity.__table__.c.confidence.server_default` present; run → FAIL (module missing).
- [ ] Implement models + migration + wiring; `pip install -r requirements.txt`.
- [ ] `alembic upgrade head` against the running stack DB → `0002_state_engine (head)`. `alembic downgrade -1 && alembic upgrade head` round-trip clean.
- [ ] `pytest -q` green; commit `feat(state): schema + ORM + migration 0002 (arch §1)`.

### Task 2: Obsidian parser
**Files:** Create `app/integrations/obsidian/__init__.py`, `client.py` (start: `ParsedNote`/`CheckboxItem` dataclasses, `parse_note`, `walk_vault` — §3.2 regexes verbatim, malformed-YAML fallback, exclude dirs incl. managed folder, file/size caps, NFC+POSIX normalization). Test `tests/unit/test_obsidian_parser.py` (§9 row 1 cases, table-driven).
- [ ] Failing tests (frontmatter, malformed YAML→body, headings, checkbox states+nesting parents via indent, inline+frontmatter tags, CRLF, empty file, exclude dirs, oversize skip) → implement → green → commit.

### Task 3: `external_id` scheme + ObservedEvent emission
**Files:** Extend `client.py`: `external_id_for_note(source_id, rel_path, frontmatter)`, `external_id_for_task(source_id, rel_path, norm_text, ordinal)`, `normalize_checkbox_text(raw_line)` (strip indent/marker/state, collapse ws), and `events_for_note(source_id, rel_path, parsed, observed_at) -> list[ObservedEvent]` applying mapping §3.4 (kinds: `obsidian.note|task|goal|project|decision`; payload carries title/summary/status/attributes + relation hints `{part_of_project, derived_from_note, parent_task_ordinal, mentions}`). Test `tests/unit/test_obsidian_external_id.py` (§9 row 2 cases: toggle-stable, edit→new id, identical-text ordinals stable under distinct-task reorder, `founderos_id` override, NFC).
- [ ] Failing tests → implement → green → commit.

### Task 4: Managed-folder write jail
**Files:** Extend `client.py`: `ManagedFolderViolation`, `validate_vault_path(path)` (§6 rules 1–6), `write_managed(vault_root, managed_folder, relative_path, content)` (§4 steps 1–4), `prune_managed(vault_root, managed_folder, keep: set[str])` (§4.5). Test `tests/unit/test_obsidian_managed_jail.py` (§4 battery verbatim: `../escape.md`, `a/../../b.md`, `/etc/passwd`, `..\\win.md`, `FounderOS/../Notes.md`, empty, symlinked-subdir-out → reject; symlinked vault root → allow; prune only deletes owned `.md` absent from keep-set).
- [ ] Failing battery → implement → green → commit.

### Task 5: Write-gate
**Files:** Create `app/state/write_gate.py`: `EntityCandidate` (type, title, summary/body, frontmatter_keys, tags, has_headings), `GateDecision` enum, `evaluate(candidate) -> (GateDecision, reasons)` — §2.3 hard rejects 1–5 + borderline (a)(b)(c) verbatim (filler set + daily-note regex as constants); `judge(candidate, provider, timeout_s) -> (keep, reason)` — one `generate()` call, temperature 0, strict-JSON parse with fail-open. Budget enforcement lives in the reconciler (Task 8), not here. Test `tests/unit/test_state_write_gate.py` (§9 row 3, table-driven; fake provider for judge paths incl. timeout→accept@0.5 signal).
- [ ] Failing tests → implement → green → commit.

### Task 6: Dedup + embedder factory
**Files:** Modify `app/retrieval/embeddings.py`: `get_default_embedder(redis)` factory (replicate `knowledge_routes._get_embedder` selection; do NOT import route modules). Create `app/state/dedup.py`: `embed_text_for(entity)` (§2.4 format), `find_similar(db, user_id, entity_type, vec, threshold)` — SQL with the F3 cast `CAST(1 - (embedding <=> CAST(:vec AS vector)) AS float8)`, top-5, scope filters; `merge(existing, candidate, observation) -> changes` implementing the §2.5 table exactly (confidence `min(0.99, old + (1-old)*0.15)`, alias cap 5, status-if-newer, summary-if->20%-longer). Test `tests/unit/test_state_dedup.py` (fake embedder + fake rows; numeric asserts on the merge table).
- [ ] Failing tests → implement → green → commit.

### Task 7: Renderer (pure)
**Files:** Create `app/state/renderer.py`: `render(entities, relations, now) -> dict[str, str]` — §2.6 files/grouping/sorting/footer/slug rules; ZERO filesystem imports. Test `tests/unit/test_state_renderer.py` (deterministic byte-identical re-render, grouping, done-cap 50, footer, slug fallback, and the import-hygiene assertion: module source has no `open(`/`write_text`).
- [ ] Failing tests → implement → green → commit.

### Task 8: Reconciler + RAG mirror
**Files:** Create `app/state/reconciler.py` (`Reconciler.reconcile_event(event)` — §2.2 steps 1–8, per-event commit, judge budget counter, hard-resolution order a/b) and `app/state/mirror.py` (§7: `state://` key, unchanged short-circuit is upstream, delete-then-reingest via existing `Ingester`). Unit-test the pure parts (`tests/unit/test_state_reconciler_logic.py`: payload canonicalization/content_hash stability, resolution-order decision table with stub lookups); DB-bound behavior is covered by the live E2E (Task 12).
- [ ] Failing unit tests → implement → green; `pytest -q` all green → commit.

### Task 9: ObsidianAdapter + fixture vault
**Files:** Create `app/integrations/obsidian/adapter.py` (§3.1 verbatim: capabilities OBSERVE|SYNC|HEALTH, `observe`, `observe_source`, `sync` (write_managed/prune only), `check_source` (§6, never mutates), idempotent `register_adapter()`); `tests/fixtures/obsidian_vault/` (§9 layout verbatim — 8 files incl. `Idea copy.md` dedup case, `todo.md` gate-reject, `Templates/` excluded). Test `tests/unit/test_obsidian_adapter.py` (observe_source on the fixture emits expected event set/kinds/ids; sync refuses paths outside jail by construction — mock write_managed and assert only relative paths passed).
- [ ] Failing tests → implement → green → commit.

### Task 10: Service + Celery task
**Files:** Create `app/state/service.py` (`StateService.run_sync(source_id, user_id, direction)` — §2.1 composition: registry lookup, lazy provider, observe→reconcile→mirror→render→adapter.sync→report/status/last_synced_at; render pulls ALL user entities) and `app/tasks/state_tasks.py` (`state_sync_task` per `agent_tasks.py` pattern; Redis `SET NX EX 900` lock `state_sync:{source_id}`, release in finally; status transitions active→syncing→active|error).
- [ ] Implement (service logic is integration-level — proven by Task 12 live E2E; keep a unit test only for the lock-key/status helper if extracted). `pytest -q` green → commit.

### Task 11: API routes + wiring  → **eng-security gate**
**Files:** Create `app/api/state_routes.py` (§5 table exactly: 9 endpoints, Pydantic models, 202-enqueue sync with 409 lock/paused, provenance-complete `EntitySummary`, scoped-404s). Modify `app/main.py` (router + `register_obsidian_adapter()` in lifespan). Test `tests/unit/test_state_routes_models.py` (validation shapes: bad vault path→422 payload, direction literal, limit cap).
- [ ] Failing validation tests → implement → green; live smoke: `POST /api/state/sources` with the fixture vault path (dev bypass) → 201; `GET /api/state/sources` shows health.
- [ ] Commit, then dispatch **eng-security** on the Task 11 diff (new authed surface + user-supplied filesystem paths + subprocess-free but write-capable sync). Apply its should-fixes before proceeding.

### Task 12: Live E2E
**Files:** Create `tests/live/test_state_obsidian_live.py` — §9 live scenario verbatim (temp-copied fixture vault; register → sync → poll → entities+relations+provenance asserts → idempotent re-sync (zero new, `unchanged == observed`) → checkbox toggle → same-entity status flip → `FounderOS/` rendered + non-managed hash invariance → `state://` RAG rows, no dupes). Provider-aware timeouts (rule 5); structure-only LLM asserts (rule 4).
- [ ] Test fails (red) only until stack restarted with new code; run `pytest tests/live/test_state_obsidian_live.py -m live -q` → green. Full `pytest -m live -q` (whole tier incl. Phase 0 suites) → green. Commit.

### Task 13: Docs, gates, close-out, PR
- [ ] `docs/architecture.md` State Engine section → as-built (§11 docs step); `.env.example` Docker vault-mount comment; `schema.sql` secondary sync (§1.7).
- [ ] Task 011 file: check off acceptance criteria with evidence; record gate outcomes.
- [ ] Cold restart → `pytest -q` + `pytest -m live -q` + `turbo test/lint/check-types` → all green with outputs captured.
- [ ] Dispatch **eng-reviewer** (full branch diff vs this plan + architecture), fix findings; then **eng-qa** vs task 011 acceptance criteria (US-1..4 + cross-cutting + success metrics).
- [ ] Retro (§9 constitution), task 011 → completed, roadmap Phase 1 → done/Shipped, memory update, push, CI green at HEAD, PR to main.

## Self-review notes
- Spec coverage: US-1 (Tasks 2,3,8,9,10,11,12), US-2 (4,7,9,12), US-3 (5,6,12), US-4 (1,11,12), cross-cutting auth/Alembic/vault-docs (1,11,13), success metrics (12,13). Architecture §§1–11 each map to a task; §10 guardrails restated in constraints.
- No placeholders: every task names exact files + the architecture § that carries the full column/signature/rule detail (committed doc, same repo — not TBD). Test case lists are enumerated per §9.
- Type consistency: names (`write_managed`, `evaluate`, `find_similar`, `merge`, `render`, `run_sync`, `state_sync_task`, `register_adapter`) match architecture §§2–8 verbatim.
