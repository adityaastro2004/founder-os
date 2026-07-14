---
id: 016
title: Alembic baseline — one-command DB bootstrap for fresh environments
status: backlog
stage: product
owner: eng-product
created: 2026-07-11
dependencies: []
links:
  - docs/architecture.md
  - founder-os/apps/api/schema.sql
  - founder-os/apps/api/alembic/versions/
  - scripts/deploy-server.sh
---

# 016 — Alembic baseline: one-command DB bootstrap

> Lives in `tasks/backlog/` → `tasks/active/` → `tasks/completed/` (move the file as
> state changes — the folder is authoritative).

## Objective

Make `alembic upgrade head` the single, complete way to build the Founder OS
database from an empty Postgres, so fresh environments (new server, teammate
laptop, CI) never hit missing-table/extension errors again.

## Problem (discovered 2026-07-11 during the EC2 production deploy)

Schema truth is fragmented across four sources, and no documented path applies
them in order:

1. `apps/api/schema.sql` — base DDL (users, extensions, ~30 tables). Nothing
   applies it: `start.sh` only runs alembic; the app's `init_db()` is a
   connectivity check only.
2. `apps/api/migrations/00{2..5}*.sql` — raw SQL files applied by hand at some
   point; never run by CD.
3. Alembic `0001`/`0002` — assume schema.sql was already applied (fail on a
   fresh DB: missing `uuid-ossp` extension, then missing `users` table).
4. At least one ORM-only column has existed with no DDL source
   (`founder_profiles.primary_goal_description`).

The production DB was rebuilt manually (schema.sql → alembic → ORM reconcile);
`scripts/deploy-server.sh` runs `alembic upgrade head` on every deploy and
silently depends on that hand-built starting point.

## Acceptance criteria

- [ ] A squashed Alembic baseline revision creates the full current schema —
      extensions (`uuid-ossp`, `pg_trgm`, `vector`), all tables/indexes — on an
      empty database with `alembic upgrade head` alone.
- [ ] Existing databases (dev laptops, EC2 prod) upgrade cleanly: baseline is
      stamped/skipped for DBs that already have the schema (alembic
      `version_table` reconciliation documented and tested against a copy of
      prod).
- [ ] `schema.sql` and `migrations/*.sql` are either deleted or clearly marked
      as generated/historical (single source of truth = alembic + ORM models).
- [ ] ORM models and migrations agree: an autogenerate diff against head is
      empty (no ORM-only columns).
- [ ] Fresh-bootstrap proof recorded: `docker compose up postgres` → `alembic
      upgrade head` → `python -c "from app.main import app"` + smoke query, on
      a clean volume, output pasted in this task.
- [ ] `start.sh` and docs/architecture.md updated to describe the single path.

## Success metrics

- Time-to-first-run for a fresh environment drops to one command after
  `docker compose up`.
- Zero schema-drift incidents on deploys (CD `alembic upgrade head` is
  sufficient forever after).

## Out of scope

- Data migrations/backfills beyond schema shape.
- Downgrade paths below the new baseline (baseline is the floor).

## Notes

- Rule 8 (CLAUDE.md): schema changes go through Alembic — this task is what
  makes that rule actually executable end-to-end.
- Coordinate with the EC2 prod DB (backup exists on the server from the
  2026-07-11 rebuild) before stamping.
