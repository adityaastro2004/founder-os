---
id: 016
title: Alembic baseline migration — single-source DB bootstrap
status: done
stage: done
owner: —
created: 2026-07-11
dependencies: []
links: [reports/2026-07-03-phase0-audit.md]
---

# 016 — Alembic baseline migration — single-source DB bootstrap

> Lives in `tasks/backlog/` → `tasks/active/` → `tasks/completed/` (move the file as
> state changes — the folder is authoritative).

## Objective

Make `alembic upgrade head` alone produce a complete, ORM-consistent database on a
fresh Postgres, so no environment ever again needs the manual `schema.sql` +
`migrations/*.sql` + hand-ALTER dance. Behavior-preserving for existing databases.

## Context (incident 2026-07-11)

Production onboarding 500'd with `column founder_profiles.primary_goal_description
does not exist`. Root cause: schema truth is fragmented across four sources, and CD
only ever runs alembic:

1. `apps/api/schema.sql` — base tables (30) + extensions + seed INSERTs
2. `apps/api/migrations/002..005*.sql` — planner/memory/chat/intelligence/research
   tables; **applied by no pipeline**
3. `apps/api/alembic/versions/0001, 0002` — reconciling deltas; `0002` does plain
   creates with FKs to `users`, so on an empty DB `alembic upgrade head` **fails**
4. ORM-only columns — `founder_profiles.primary_goal_description` exists in
   `app/models.py` only, in no SQL file at all

The prod DB was rebuilt by hand (schema.sql + 002–005 + ORM reconcile; a copy of the
one-off script is on the server at `apps/api/reconcile_schema.py`). This task makes
that one-off unnecessary and impossible to need again.

## Acceptance criteria

- [ ] On an **empty** Postgres 16 + pgvector database, `alembic upgrade head`
      succeeds and creates every table/column the ORM maps (`app/models.py`,
      `app/planner_models_db.py`), all required extensions, and the seed rows the
      app depends on (subscription_plans, workflow_templates).
- [ ] Resulting schema has no missing columns vs. ORM metadata (automated
      reflection-diff check, not eyeballing).
- [ ] On an **existing** database already at revision 0002 (e.g. production),
      `alembic upgrade head` is a no-op — no errors, no destructive statements.
- [ ] On a **schema.sql-seeded** database with no alembic history, upgrade
      completes without duplicate-object errors (idempotent/guarded creates).
- [ ] An automated test exercises the fresh-DB path against a throwaway Postgres
      container and asserts ORM parity.
- [ ] ADR recorded in docs/decisions.md; docs/architecture.md data-model section
      updated to name the migration chain as the single bootstrap path.

## Stage log

- 2026-07-11 — opened at architect stage (refactor workflow; behavior-preserving
  infra). Characterization of current behavior done during the incident: empty-DB
  `alembic upgrade head` fails at 0002 (FK to absent `users`).
- 2026-07-11 — architecture complete (eng-architect). ADR-011 appended to
  docs/decisions.md. Design below; handed to eng-executor.
- 2026-07-12 — implementation complete (eng-executor, worktree
  `schema-baseline-migration`). Implemented exactly §A–§I; handed to eng-qa.

  **Changed files** — created: `apps/api/alembic/versions/0000_baseline.py`,
  `apps/api/tests/migrations/{__init__,test_schema_baseline}.py`,
  `apps/api/tests/fixtures/legacy_schema_2026-07-11.sql` (byte-copy of pre-016
  schema.sql, taken before editing it); edited:
  `apps/api/alembic/versions/0001_workflow_engine.py` (re-parent only),
  `apps/api/schema.sql` (banner + `primary_goal_description` + absorbed 002–005
  DDL appended verbatim), `apps/api/pytest.ini` (marker + addopts),
  `.github/workflows/ci.yml` (migrations step; unit step's `-m` also excludes
  `migrations` so the new tier isn't double-run), `docs/architecture.md`
  (data-model section), `standards/testing.md` (4th tier); deleted:
  `apps/api/migrations/002..005*.sql` (+ empty dir). `0002_state_engine.py`
  untouched. One-time autogenerate scaffold generated against an empty
  pgvector DB, post-processed per §B.2, then deleted (nothing imports `app.*`;
  alembic's quote-stripping had mangled the ORM's `'[]'::jsonb` server
  defaults to invalid `[]'::jsonb` — fixed to `sa.text("'[]'::jsonb")` and
  verified via `column_default` on a fresh DB).

  **How verified** (all against throwaway `pgvector/pgvector:pg16`, alembic run
  as CD runs it — `python -m alembic upgrade head` with env-var DSNs):
  1. Fresh empty DB → exit 0, full chain `0000 → 0001 → 0002`; reflection-diff:
     40/40 ORM tables, `missing tables: []`, `missing columns: []`; extensions
     `{uuid-ossp, pg_trgm, vector}`, `memory_temporal_score` +
     `update_updated_at_column` present; 3 research tables; 4+4 seed rows.
  2. Second `upgrade head` on the same DB → exit 0, zero `Running upgrade`
     lines, `alembic_version` + seed counts unchanged.
  3. Legacy-fixture-seeded DB (no history) → exit 0, no duplicate-object
     errors; `founder_profiles.primary_goal_description` 0 → 1 (the incident
     column lands); `subscription_plans` count still 4; `agents` rows (7)
     untouched; full name-level parity.
  4. Fixture DB + `alembic stamp head` → `upgrade head` exit 0, no `Running
     upgrade` output, version unchanged; `alembic heads` shows exactly one
     head: `0002_state_engine (head)`.
  5. `pytest -m migrations -q` → `4 passed, 180 deselected in 6.18s`; default
     `pytest -q` → `164 passed, 20 deselected in 1.22s` (unit tier unchanged;
     16 live + 4 migrations deselected). Bonus (CI mirror): re-synced
     schema.sql applies cleanly via `psql -v ON_ERROR_STOP=1` (notices only,
     incl. the documented `idx_knowledge_items_category` name-collision no-op);
     `compileall` + ruff critical selectors clean on the new files.

- 2026-07-12 — **QA PASS** (eng-qa). Independent re-verification — executor's
  claims re-run from scratch, not taken on faith. Environment: throwaway
  `pgvector/pgvector:pg16` on `:55434`; interpreter = main checkout's
  `apps/api/.venv` (worktree has none); cwd = worktree `apps/api`; no `.env`
  present (subprocess env vars steer alembic, as designed).

  **Per-criterion results (all PASS):**

  1. *Empty-DB bootstrap* — PASS. Harness: `test_fresh_db_bootstrap` green.
     Independent e2e without the harness: fresh DB `qa016_e2e` →
     `python -m alembic upgrade head` (env DSNs) → exit 0, chain
     `→ 0000_baseline → 0001_workflow_engine → 0002_state_engine`; psql:
     `primary_goal_description` count = 1, `memory_temporal_score` in
     `pg_proc` = 1, 44 public tables (40 ORM + 3 research + alembic_version),
     extensions `{pg_trgm, uuid-ossp, vector}`, `alembic_version` =
     `0002_state_engine`, `alembic heads` = exactly `0002_state_engine (head)`.
  2. *ORM reflection parity (automated)* — PASS. `_assert_orm_parity` in
     `tests/migrations/test_schema_baseline.py` diffs all
     `Base.metadata.tables` (same 3 modules as `alembic/env.py`) against
     `sa.inspect(engine)`; runs in cases 1 and 3; green.
  3. *At-revision-0002 DB is a no-op* — PASS. Harness case 4
     (fixture + `stamp head` → upgrade → no `Running upgrade`, version
     unchanged) green; independently, second `upgrade head` on `qa016_e2e`
     (already at head): exit 0, zero migration lines emitted.
  4. *schema.sql-seeded DB, no history* — PASS. Harness case 3 green
     (fixture verified **byte-identical** to pre-016 `schema.sql` via
     `git show HEAD:…schema.sql | diff -`): no duplicate-object errors,
     incident column lands, `subscription_plans` count stays 4.
  5. *Automated fresh-DB test vs throwaway container* — PASS.
     `MIGRATIONS_ADMIN_DSN=postgresql://founder:founder@localhost:55434/postgres
     pytest -m migrations -q` → `4 passed, 180 deselected in 5.35s`.
     Default `pytest -q` → `164 passed, 20 deselected in 0.86s` — unit tier
     identical to baseline; migrations + live deselected by `pytest.ini`.
  6. *ADR + docs* — PASS. ADR-011 present in `docs/decisions.md`;
     `docs/architecture.md` data-model section names
     `alembic upgrade head` as the single bootstrap path (schema.sql =
     secondary artifact); `standards/testing.md` gains the `migrations` tier
     row + CI note.

  **Structural checks:** `migrations/002..005*.sql` deleted, directory gone;
  schema.sql carries the DO-NOT-APPLY banner + `primary_goal_description`
  (line 49); `git diff --stat` empty for every do-not-touch file
  (`0002_state_engine.py`, `alembic/env.py`, `alembic.ini`, `app/models.py`,
  `app/planner_models_db.py`, `app/state/models.py`, `app/database.py`,
  `scripts/deploy-server.sh`, `start.sh`, `.claude/settings.json`).

  **Executor judgment calls reviewed — none threatens any criterion:**
  - *CI unit-step marker edit* (`-m "not live"` → `"not live and not
    migrations"`): required — the step's explicit `-m` overrides `pytest.ini`
    addopts, so without it the unit step would double-run the migration tier.
    Nothing is lost: the dedicated `pytest -m migrations -q` step follows.
  - *`sa.text("'[]'::jsonb")` default freeze*: grep confirms zero mangled
    `[]'::jsonb` literals remain in `0000_baseline.py`; live check on the
    fresh DB shows `column_default = '[]'::jsonb` for
    `user_profiles_intel.{likes,goals,preferred_agents}` — matches the ORM.
  - *`idx_knowledge_items_category` canonicalization*: schema.sql's
    `(category)` btree wins the name; 005's same-named `(user_id, category)`
    partial index historically **never applied** (`IF NOT EXISTS` collided on
    every real DB), so the baseline reproduces actual prod shape. Verified in
    the fresh DB: `pg_indexes` shows `USING btree (category)`. Index-level
    parity is explicitly out of scope (§I).

  **Observation for eng-reviewer (non-blocking):** `.github/workflows/
  deploy.yml` carries an uncommitted comment-only edit (SSM/OIDC trust-policy
  wording) that is **not** in the executor's declared changed-files list and
  not part of the 016 design. No functional change; reviewer should decide
  whether it ships with this task or is split out.

  Verdict: **all 6 acceptance criteria PASS**. Handed to eng-reviewer
  (frontmatter → stage: reviewer). Throwaway container removed after the run.

---

## Architecture (eng-architect, 2026-07-11 — see ADR-011)

All paths below are relative to `founder-os/apps/api/` unless prefixed with the
git root. **Design only — the executor implements exactly this; deviations go back
through the architect.**

### A. Verified facts the design rests on

- `0002_state_engine` already has `_has_table` guards, but on an **empty** DB it
  still fails: FKs to absent `users` + `uuid_generate_v4()` / `Vector(1536)` need
  the `uuid-ossp` / `vector` extensions. A guard cannot save it; the *prerequisites*
  are missing. Therefore **no revision placed after 0002 can fix empty-DB bootstrap**
  without editing 0002 — which is forbidden (never weaken migrations on
  already-migrated DBs). Re-rooting is the only clean topology.
- ORM tables total **40** across three modules (all already imported by
  `alembic/env.py`): `app/models.py` (32), `app/planner_models_db.py` (4),
  `app/state/models.py` (4).
- `migrations/005` also defines **3 non-ORM tables** (`research_runs`,
  `tracked_competitors`, `research_sources`). No app code references them
  (crawler_routes stores competitors in `memory_pages`), but the hand-rebuilt prod
  has them.
- `memory_temporal_score(...)` (from `migrations/002`) is **load-bearing** — 8 call
  sites in `app/memory/manager.py`. No ORM reflection check can see it; the baseline
  must create it or memory retrieval breaks on any fresh DB.
- `schema.sql` also defines `update_updated_at_column()` + 8 `updated_at` triggers
  (the ORM has no `onupdate` on those tables — the triggers are the behavior) and
  3 views (`tasks_pending_approval`, `user_dashboard_summary`,
  `agent_performance_summary`; unused by app code, present in prod).
- Seed unique keys verified: `workflow_templates.slug` UNIQUE,
  `subscription_plans.name` UNIQUE (`agents.name` UNIQUE too, but see below) →
  `ON CONFLICT … DO NOTHING` is well-defined.
- `agents` rows do **not** need seeding: `sync_agents_to_db` (ADR-004,
  `app/agents/registry.py:1152`) inserts/updates every `AGENT_CLASSES` entry at app
  startup. Seeding generic prompts in the migration would duplicate that mechanism.
- `config.py` uses stock pydantic-settings ordering (real env vars beat
  `apps/api/.env`), so tests can steer `alembic` via subprocess env. `alembic.ini`
  has `prepend_sys_path = .` → run alembic with `cwd=apps/api`.
- CI's backend job (`.github/workflows/ci.yml`) already provisions
  `pgvector/pgvector:pg16` + applies `schema.sql` — the migration test runs there
  with zero new infrastructure.
- `alembic_version.version_num` is VARCHAR(32); `"0000_baseline"` (13 chars) fits.

### B. Decisions (design questions 1–5)

1. **Topology — re-rooted baseline.** New root revision `0000_baseline`
   (`down_revision = None`); re-parent `0001_workflow_engine` with the one-line edit
   `down_revision = "0000_baseline"` (+ fix its docstring `Revises:` line);
   `0002_state_engine` untouched and **remains the sole head**. Prod at 0002 == head
   → structurally a no-op. Rejected: post-0002 head (see fact 1).
2. **DDL source — frozen/inlined, generated once.** The executor generates the
   baseline DDL one time — `alembic revision --autogenerate` against an *empty*
   throwaway DB emits `op.create_table(...)` for all 40 ORM tables; then: **delete**
   the 4 state tables from the output (0002 owns their create + downgrade), **add**
   verbatim-SQL blocks for everything the ORM can't express (below). The result is
   inlined and static forever. The migration file must **never import `app.*`**
   (models drift; migrations are frozen history — 0001's docstring precedent).
3. **Idempotence — house guard pattern (from 0001).** Per-table `_has_table` guard;
   indexes created only inside the same guard branch (if the table pre-exists from
   schema.sql, its indexes exist); `_has_column` add-if-missing reconcile pass for
   ORM-only columns on schema.sql-owned tables; `CREATE EXTENSION IF NOT EXISTS`;
   `CREATE OR REPLACE FUNCTION/VIEW`; `CREATE OR REPLACE TRIGGER` (PG16 supports
   it); seeds `ON CONFLICT DO NOTHING`.
4. **Extensions + seeds live in the baseline** (first and last steps respectively —
   see order in §C). Seeds = `workflow_templates` (4 rows, conflict target `slug`)
   and `subscription_plans` (4 rows, conflict target `name`), copied verbatim from
   schema.sql with the ON CONFLICT clause appended. **No `agents` seed** (fact 6).
5. **Artifact disposition.** Delete `migrations/002..005*.sql` (absorbed; git
   history preserves them). Keep `schema.sql` as the human-readable **secondary**
   artifact: add a banner ("DO NOT APPLY — bootstrap is `alembic upgrade head`;
   kept in sync per CLAUDE.md §5.8") and re-sync it to full current truth (add
   `founder_profiles.primary_goal_description` + the 002–005 tables with
   `IF NOT EXISTS`), so CI's psql-apply step keeps validating a *complete* snapshot.

### C. The baseline migration — `alembic/versions/0000_baseline.py`

- `revision = "0000_baseline"`, `down_revision = None`, filename
  `0000_baseline.py` (matches the `NNNN_slug` house style).
- Docstring must state: frozen snapshot as of 2026-07-11; sources (ORM metadata +
  schema.sql + migrations/002–005); the superuser note for `CREATE EXTENSION`
  (docker/CI/current prod are fine; managed Postgres may need extensions
  pre-enabled); and that `downgrade()` is deliberately a no-op.
- Internal order (single `upgrade()`):
  1. **Extensions**: `uuid-ossp`, `pg_trgm`, `vector` — `op.execute('CREATE
     EXTENSION IF NOT EXISTS …')`.
  2. **Guarded table creates in FK order** (each with its indexes in the same
     branch). 36 ORM tables (DDL from autogenerate — the ORM is the authority for
     columns/defaults):
     `users` → `founder_profiles` (incl. `primary_goal_description`) → `agents` →
     `user_agent_configs` → `workflow_templates` → `workflows` (incl.
     `n8n_workflow_id`) → `workflow_executions` (incl. `step_state`) → `tasks` →
     `task_dependencies` → `knowledge_items` → `context_usage` →
     `business_metrics` → `integrations` → `integration_syncs` → `outputs` →
     `agent_analytics` → `task_feedback` → `learning_insights` → `notifications` →
     `notification_preferences` → `subscription_plans` → `usage_records` →
     `audit_logs` → `api_keys` → `founder_context_models` → `agent_definitions` →
     `planner_users` → `plan_history` → `memory_pages` → `memory_links` →
     `agent_runs` → `chat_messages` → `user_profiles_intel` → `user_insights` →
     `business_insights` → `content_ideas`.
     Plus 3 **non-ORM** tables copied verbatim from `migrations/005`:
     `research_runs`, `tracked_competitors`, `research_sources` (comment: dead code
     today, kept for prod parity; drop is a future task).
     Indexes include the schema.sql set, the 002 memory indexes (ivfflat on
     `memory_pages.embedding`, GIN fts/tags/entities), the 003 agent_runs/
     chat_messages indexes, the ivfflat on `knowledge_items.embedding`, and the 005
     performance indexes (only those on tables this branch just created — the 005
     indexes on `tasks`/`knowledge_items` go in those tables' branches).
  3. **Functions** (`op.execute`, `CREATE OR REPLACE`): `update_updated_at_column()`
     (schema.sql) and `memory_temporal_score(...)` (migrations/002) — verbatim.
  4. **Triggers**: the 8 `update_<table>_updated_at` triggers as
     `CREATE OR REPLACE TRIGGER …` (PG16).
  5. **Views** (`CREATE OR REPLACE VIEW`): `tasks_pending_approval`,
     `user_dashboard_summary`, `agent_performance_summary` — verbatim.
  6. **Column-reconcile pass** (`_has_column` guards; this is what fixes the
     seeded-DB path): `founder_profiles.primary_goal_description TEXT NULL`. If the
     seeded-path test (§E case 3) reveals more ORM⊃schema.sql deltas, add each here
     with the same guard — the reconcile list is *discovered by the test, then
     frozen*.
  7. **Seeds** (`op.execute`, verbatim INSERTs from schema.sql +
     `ON CONFLICT (slug|name) DO NOTHING`): 4 `workflow_templates`,
     4 `subscription_plans`.
- `downgrade()`: **explicit no-op** with a comment — the baseline is the root and
  may cover schema that pre-existed alembic; a destructive reverse is never safe
  (same philosophy as 0001's downgrade). Downgrading below the root is meaningless.
- Helper functions `_inspector/_has_table/_has_column` copied from 0001 (module-
  local, as in 0001/0002 — migrations don't share imports).

### D. Upgrade-path walkthrough (all three starting states)

1. **Empty DB** (fresh Postgres 16 + pgvector image):
   `0000` creates extensions → all 39 guarded creates fire in FK order → functions,
   triggers, views → reconcile pass finds columns present (just created) → seeds
   insert. `0001`: every `_has_table` true → skips creates; both `_has_column`
   guards true → skips. `0002`: state tables absent → plain creates now succeed
   (`users` and `vector` exist). End: head, full schema, seeds present. ✔
2. **schema.sql-seeded DB, no alembic history** (legacy dev DB):
   `0000`: extensions no-op; the ~30 schema.sql tables skip via `_has_table`; the
   002–005 tables (absent from schema.sql) are created; `CREATE OR REPLACE`
   functions/views and `CREATE OR REPLACE TRIGGER` overwrite identically; reconcile
   pass **adds `founder_profiles.primary_goal_description`** (the incident column);
   seeds hit `ON CONFLICT DO NOTHING` (rows already there — no duplicates). `0001`
   skips (guards). `0002`: schema.sql (current) already contains the state tables →
   `_has_table` guards skip; on an *older* schema.sql seed without them, 0002
   creates them — both fine. End: head, ORM parity. ✔
3. **Prod at revision 0002**: `alembic_version` says `0002_state_engine`, which is
   still the head of the re-rooted chain → alembic executes **zero** migrations.
   `0000` is an ancestor prod never runs (alembic only walks current→head). No
   statement is emitted. ✔ (A dev DB stamped at `0001` similarly runs only `0002`,
   exactly as before — behavior unchanged.)

### E. Test plan (design question 6)

**New pytest tier `migrations`** — needs a reachable Postgres but *not* the app
stack, so it must be excluded from the service-free unit tier and from `live`:

- `pytest.ini`: add marker `migrations`; change addopts to
  `-m "not live and not migrations"`.
- Run locally with `pytest -m migrations` against any pgvector Postgres (the
  compose one, or `docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=founder
  -e POSTGRES_USER=founder pgvector/pgvector:pg16`).
- CI: add one step to the existing backend job (after unit tests — the pg16
  service is already up): `pytest -m migrations -q`. This makes "ORM column with
  no migration" a CI failure forever.

**New file `tests/migrations/test_schema_baseline.py`** (+ `__init__.py`):

- Harness: admin DSN from env `MIGRATIONS_ADMIN_DSN`, default
  `postgresql://founder:founder@localhost:5432/postgres`. For each case, create a
  throwaway database (`fos_mig_<case>_<hex8>`) via psycopg2 autocommit, drop it in
  teardown. Connection failure = **test failure with an actionable message**, not a
  skip (the marker is opt-in locally, mandatory in CI).
- Alembic is exercised the way CD runs it: `subprocess.run([sys.executable, "-m",
  "alembic", "upgrade", "head"], cwd=<apps/api>, env={**os.environ,
  "DATABASE_URL": <async dsn>, "DATABASE_URL_SYNC": <sync dsn>,
  "APP_ENV": "development"})` — real env vars beat `.env` (pydantic-settings
  default), so a founder `.env` can't leak into the test.
- Reflection-diff helper: build a sync engine on the throwaway DB, import
  `app.models`, `app.planner_models_db`, `app.state.models` (the same three
  modules `alembic/env.py` imports), and assert for every table in
  `Base.metadata.tables`: table exists, and every ORM column name exists
  (`sa.inspect(engine).get_columns(...)`). **Name-level** parity only — type/
  default/index parity is explicitly out of scope (v2 hardening).
- Cases:
  1. **Fresh bootstrap**: empty DB → `upgrade head` (exit 0) → reflection-diff
     passes; extensions present (`pg_extension`); `memory_temporal_score` and
     `update_updated_at_column` present (`pg_proc`); the 3 research tables exist;
     `subscription_plans` has the 4 seed names and `workflow_templates` the 4 seed
     slugs; `alembic_version` matches the script head.
  2. **Idempotence**: run `upgrade head` a second time on the case-1 DB → exit 0,
     `alembic_version` and table set unchanged.
  3. **Legacy schema.sql-seeded, no history**: new DB → apply
     `tests/fixtures/legacy_schema_2026-07-11.sql` (a **frozen byte-copy of
     today's pre-016 schema.sql** — fixture, so future schema.sql edits can't
     silently weaken this case) via psycopg2 (single multi-statement execute
     handles the dollar-quoted bodies; CI proves the file is valid psql too) →
     `upgrade head` → exit 0, **no duplicate-object errors**, reflection-diff
     passes (this is the case that proves `primary_goal_description` lands), and
     `SELECT count(*) FROM subscription_plans` == 4 (seeds not duplicated).
  4. **Stamped-at-head no-op (prod shape)**: new DB → apply the legacy fixture →
     `alembic stamp head` (today head == `0002_state_engine`, i.e. prod's exact
     state) → `upgrade head` → exit 0, `alembic_version` unchanged, stdout contains
     no `Running upgrade` line. Also assert the script directory has exactly **one
     head** (pins the topology: nobody accidentally created a second root/branch).

Definition of done for the executor: all four cases green locally
(`pytest -m migrations`) **and** the unmodified unit tier still green (`pytest`),
with output pasted into this file's stage log.

### F. File list for the executor (exact)

Create:
1. `founder-os/apps/api/alembic/versions/0000_baseline.py` — the baseline (§C).
2. `founder-os/apps/api/tests/migrations/__init__.py`
3. `founder-os/apps/api/tests/migrations/test_schema_baseline.py` — §E.
4. `founder-os/apps/api/tests/fixtures/legacy_schema_2026-07-11.sql` — frozen
   byte-copy of the current (pre-016) `schema.sql`. Create this copy **before**
   editing schema.sql.

Edit:
5. `founder-os/apps/api/alembic/versions/0001_workflow_engine.py` — only
   `down_revision = "0000_baseline"` + the docstring `Revises:` line. Nothing else.
6. `founder-os/apps/api/schema.sql` — deprecation/pointer banner; add
   `primary_goal_description` to `founder_profiles`; append the 002–005 DDL
   (`IF NOT EXISTS` style) so the secondary artifact is complete again.
7. `founder-os/apps/api/pytest.ini` — `migrations` marker + addopts exclusion.
8. `.github/workflows/ci.yml` — one step in the backend job: `pytest -m migrations -q`.
9. `docs/architecture.md` — data-model section: name `alembic upgrade head` as the
   **single** bootstrap path; schema.sql = secondary human-readable artifact;
   migrations/*.sql removed.
10. `standards/testing.md` — add the `migrations` tier row to the tier table (needs
    Postgres only; opt-in locally, mandatory in CI).

Delete:
11. `founder-os/apps/api/migrations/002_planner_and_memory.sql`
12. `founder-os/apps/api/migrations/003_agent_runs_and_chat.sql`
13. `founder-os/apps/api/migrations/004_user_intelligence.sql`
14. `founder-os/apps/api/migrations/005_indexes_and_research.sql`
    (remove the now-empty `migrations/` directory)

Do NOT touch: `0002_state_engine.py`, `alembic/env.py`, `alembic.ini`,
`app/models.py`, `app/planner_models_db.py`, `app/state/models.py`, `app/database.py`,
`scripts/deploy-server.sh`, `start.sh`, `.claude/settings.json`.

### G. API / integration points

- **API surface: none.** No routes, no `main.py` changes, no auth changes.
- **CD** (deploy.yml → on-server `scripts/deploy-server.sh`) and `start.sh` already
  run `alembic upgrade head` — unchanged; they simply start working on fresh DBs.
- **Alembic env** (`env.py`) already imports the three model modules — unchanged.
  Note for the future (docs edit #9): any *new* model module must be imported in
  `env.py`, or autogenerate *and* the parity test both go blind to it.
- **Celery/scheduler/agents/memory/approval gate**: untouched. The only runtime
  behavior change is that fresh DBs now get the `updated_at` triggers and
  `memory_temporal_score` (previously only present where schema.sql/002 had been
  hand-applied) — that is the *point* (parity with prod).

### H. Risks & trade-offs

- **DDL duplication (ORM vs frozen baseline)** — accepted: migrations are frozen
  history; parity is machine-enforced in CI from now on (the incident class becomes
  a test failure, not a prod 500).
- **Overlap with 0001's two columns** (`n8n_workflow_id`, `step_state`): baseline
  creates them inside `workflows`/`workflow_executions`; 0001's `_has_column`
  guards then skip. Both orders safe; 0001's downgrade semantics unchanged.
- **`CREATE EXTENSION` needs superuser** — true for the docker image, CI service,
  and current prod. Managed Postgres (RDS-style) may need extensions pre-enabled;
  documented in the migration docstring, not solved here.
- **Seeds in a migration** — insert-only + `ON CONFLICT DO NOTHING`, never updates
  existing rows → prod-safe. The big `workflow_templates` JSON is embedded verbatim
  from schema.sql (single-quoted `'…'::jsonb` literals; no interpolation).
- **Research tables are dead code** — kept for prod parity; flagged in the baseline
  docstring as candidates for a future drop migration (roadmap note, out of scope).
- **Views/`user_dashboard_summary` reference many tables** — created after all
  tables in §C order, so `CREATE OR REPLACE VIEW` always resolves.

### I. Out of scope (explicit)

- Dropping the unused research tables or the unused views (future cleanup task).
- Type-/default-/index-level reflection parity (name-level only in v1 of the test).
- `alembic check` / autogenerate-drift gating in CI (the parity test covers the
  incident class; full drift gating is a possible follow-up).
- Managed-Postgres extension provisioning (RDS-style `CREATE EXTENSION` privileges)
  — documented as an operator prerequisite, not solved here.
- Any edit to `0002_state_engine.py` or to runtime application code.
- Deleting the server-side one-off `reconcile_schema.py` (ops follow-up after this
  ships; note it in the release checklist).
- Frontend, docs site, and the 13 standalone `test_*.py` scripts.

---

## Review (eng-reviewer, 2026-07-12)

**Verdict: approve-with-nits → eng-qa.** No blockers, no should-fixes. Implementation
matches §A–§I and ADR-011; all three executor judgment calls are acceptable within
the approved design (rationale below). Nits are recordable follow-ups, none require
executor rework.

### What was independently verified (not taken from the stage log)

- Fixture `tests/fixtures/legacy_schema_2026-07-11.sql` is **byte-identical** to
  pre-016 `schema.sql` (`git show HEAD:…/schema.sql | diff -` → clean).
- Revision graph is linear `0000_baseline → 0001_workflow_engine → 0002_state_engine`,
  single head; `0002_state_engine.py` untouched; `0001` diff is exactly the
  re-parent + docstring `Revises:` line (2 hunks, nothing else).
- FK order of all 39 creates in `_TABLE_BUILDERS` walked parent-before-child
  (incl. self-refs `outputs.parent_output_id`, `memory_pages.parent_id`) — no
  forward references.
- Index-name diff fixture↔baseline: the only fixture indexes absent from the
  baseline are the 6 state-engine ones (0002-owned); every schema.sql-owned index
  is present. No index/trigger/view/function is created outside a guard or
  OR-REPLACE form.
- `0000_baseline.py` imports no `app.*` (only sqlalchemy/alembic/pgvector —
  pgvector import matches 0002 precedent). Seeds' ON CONFLICT targets verified
  UNIQUE in the legacy fixture (`workflow_templates.slug` L97,
  `subscription_plans.name` L395). Seed JSON uses raw strings so the literal `\n`
  matches schema.sql byte-for-byte.
- Test quality vs ADR-011 §6: parity check is name-level on **both** tables and
  columns (`_assert_orm_parity`, imports the same 3 modules as `alembic/env.py`);
  connection failure is a pytest **failure** with an actionable message, not a
  skip; case 4 asserts no `Running upgrade` output + exactly one head +
  `0002_state_engine`. CI unit step's explicit `-m` overrides pytest.ini addopts,
  so the marker edit there was necessary (see flag 1).
- Scope: changed/created/deleted files match §F exactly (+ ADR-011 in
  decisions.md, + the flagged pre-existing deploy.yml comment edit); the §F
  Do-NOT-touch list is untouched. `migrations/` dir removed.
- Security: no secrets in the frozen DDL, fixture, or CI edit; seeds create only
  `subscription_plans`/`workflow_templates` rows (no users/privileged rows);
  nothing touches auth or the approval gate. `py_compile` passes on both new
  Python files.

### Judgment on the three executor flags

1. **CI unit-step `-m "not live and not migrations"`** — acceptable and in fact
   *required*: the CI step passes `-m` explicitly, which overrides the pytest.ini
   addopts exclusion; without the edit the unit step would double-run the 4
   migration tests inside the "unit" step. Minimal edit, in the spirit of §E.
2. **Freezing `sa.text("'[]'::jsonb")`** — acceptable, required: raw autogenerate
   output was *invalid* SQL (alembic quote-stripping); the fix restores the ORM's
   actual server_default and was verified via `column_default`. §B.2 makes the ORM
   the authority for columns/defaults — this is compliance, not deviation.
3. **Historical index names over ORM `ix_` names** — acceptable within design:
   §C.2 specifies index DDL *verbatim* from schema.sql/002–005 for prod parity;
   index-level parity and autogenerate-drift gating are explicitly out of scope
   (§I). Consequence (future autogenerate will propose renames) is already an
   accepted ADR-011 trade-off.

### Findings

1. **nit** — `founder-os/apps/api/alembic/versions/0000_baseline.py:283-288,344-347`
   — on a legacy schema.sql-seeded DB, the table-level guard skips the whole
   branch, so the two 005-era indexes on schema.sql-owned tables
   (`idx_tasks_user_status`, `idx_knowledge_items_processing`) are never created
   there (design §D.2's "its indexes exist" premise doesn't hold for these two).
   Prod has them (hand-applied 005) and fresh DBs get them; only legacy dev DBs
   lose two performance indexes. Matches the approved design (§B.3 guard
   granularity, §I index parity out of scope). Fix: one docstring line in the
   baseline noting the limitation, or fold into the v2 index-parity follow-up.
2. **nit** — `founder-os/apps/api/schema.sql` (appended 005 block, "Knowledge
   items: category + active") — the appended `idx_knowledge_items_category
   (user_id, category)` never applies (the earlier `(category)` definition wins
   the name via IF NOT EXISTS). The baseline documents this
   (`0000_baseline.py:331-332`); the secondary artifact itself doesn't. Fix: add
   the same one-line comment here for the next human reader.
3. **nit** — `.github/workflows/deploy.yml:5-7` — comment-only edit is accurate
   (SSM-only CD; SSH-on-22 is a manual-ops path) and leaks no secrets, but it
   documents the instance's open SSH port; confirm that's acceptable if the repo
   is or becomes public.
4. **nit** — `founder-os/apps/api/tests/migrations/test_schema_baseline.py:249-258`
   — the idempotence case matches §E case 2 as written (exit 0, version + table
   set unchanged) but could also cheaply assert no `Running upgrade` output and
   stable seed counts, as the executor's manual run did. Optional hardening only.

Next stage: eng-qa (validate the four cases + unit tier against acceptance criteria).

- 2026-07-14 — eng-reviewer: **approve-with-nits** (no blockers; three executor
  flags all judged acceptable-within-design). Nits 1–2 (documentation lines in
  0000_baseline.py docstring + schema.sql 005 block) applied; nit 3 noted in the
  PR (deploy.yml comment documents the open SSH port — fine while repo access is
  controlled); nit 4 (idempotence-test hardening) left as optional follow-up.
  Task closed; moved to tasks/completed/.
