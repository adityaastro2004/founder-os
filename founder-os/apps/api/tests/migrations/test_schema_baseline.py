"""Migration tier — `alembic upgrade head` is the single DB bootstrap (task 016 / ADR-011).

Four cases, each against a throwaway database (created/dropped per test):

  1. fresh empty DB       → full bootstrap; ORM name-level parity; extensions,
                            functions, research tables, seeds, head revision
  2. idempotence          → a second `upgrade head` is a clean no-op
  3. legacy schema.sql DB → guarded upgrade; no duplicate-object errors; the
                            reconcile pass lands `founder_profiles.
                            primary_goal_description`; seeds not duplicated
  4. stamped at head      → zero migrations executed (prod shape); the script
                            directory has exactly one head

Needs a reachable pgvector Postgres with CREATEDB rights — nothing else (no app
stack, no Redis, no LLM). Configure via:

    MIGRATIONS_ADMIN_DSN   (default: postgresql://founder:founder@localhost:5432/postgres)

A connection failure FAILS these tests with an actionable message (never skips):
the marker is opt-in locally (`pytest -m migrations`) and mandatory in CI, where
the pg16 service is already provisioned.

Alembic is exercised the way CD runs it — a `python -m alembic upgrade head`
subprocess with `cwd=apps/api` — steered via DATABASE_URL / DATABASE_URL_SYNC
env vars, which beat any founder `.env` under pydantic-settings defaults.
Parity is **name-level** only (tables + columns); type/default/index parity is
explicitly out of scope (v2 hardening).
"""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import psycopg2
import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.migrations

API_DIR = Path(__file__).resolve().parents[2]  # …/founder-os/apps/api
LEGACY_FIXTURE = API_DIR / "tests" / "fixtures" / "legacy_schema_2026-07-11.sql"

ADMIN_DSN = os.environ.get(
    "MIGRATIONS_ADMIN_DSN", "postgresql://founder:founder@localhost:5432/postgres"
)

EXPECTED_EXTENSIONS = {"uuid-ossp", "pg_trgm", "vector"}
EXPECTED_FUNCTIONS = {"memory_temporal_score", "update_updated_at_column"}
RESEARCH_TABLES = {"research_runs", "tracked_competitors", "research_sources"}
SEED_PLAN_NAMES = {"free", "starter", "pro", "enterprise"}
SEED_TEMPLATE_SLUGS = {"weekly-planning", "content-creation", "product-launch", "customer-onboarding"}


# ────────────────────────────────────────────────────────────────────────────
# Harness
# ────────────────────────────────────────────────────────────────────────────

def _admin_conn():
    """Autocommit connection to the admin DB; connection failure = test failure."""
    try:
        conn = psycopg2.connect(ADMIN_DSN)
    except psycopg2.OperationalError as exc:
        pytest.fail(
            f"Cannot reach the migrations Postgres at {ADMIN_DSN!r}: {exc}\n"
            "Start one, e.g.:\n"
            "  docker run -d --rm -p 5432:5432 -e POSTGRES_USER=founder "
            "-e POSTGRES_PASSWORD=founder pgvector/pgvector:pg16\n"
            "or point MIGRATIONS_ADMIN_DSN at an existing pgvector Postgres."
        )
    conn.autocommit = True
    return conn


def _urls(dbname: str) -> dict[str, str]:
    """Derive the three DSN flavors for a throwaway DB from the admin DSN."""
    base = make_url(ADMIN_DSN).set(database=dbname)
    return {
        "async": base.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False),
        "sync": base.set(drivername="postgresql+psycopg2").render_as_string(hide_password=False),
        "psycopg2": base.set(drivername="postgresql").render_as_string(hide_password=False),
    }


@pytest.fixture
def db_factory():
    """Create throwaway databases `fos_mig_<case>_<hex8>`; drop them in teardown."""
    created: list[str] = []

    def make(case: str) -> dict[str, str]:
        name = f"fos_mig_{case}_{secrets.token_hex(4)}"
        conn = _admin_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f'CREATE DATABASE "{name}"')
        finally:
            conn.close()
        created.append(name)
        return _urls(name)

    yield make

    conn = _admin_conn()
    try:
        with conn.cursor() as cur:
            for name in created:
                cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        conn.close()


def _alembic(urls: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    """Run alembic exactly the way CD does (subprocess, cwd=apps/api)."""
    env = {
        **os.environ,
        "DATABASE_URL": urls["async"],
        "DATABASE_URL_SYNC": urls["sync"],
        "APP_ENV": "development",
    }
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=API_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


def _assert_upgrade_ok(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, (
        f"alembic exited {result.returncode}\n--- stdout ---\n{result.stdout}"
        f"\n--- stderr ---\n{result.stderr}"
    )


def _apply_legacy_fixture(urls: dict[str, str]) -> None:
    """Apply the frozen pre-016 schema.sql byte-copy (single multi-statement
    execute — psycopg2 handles the dollar-quoted function bodies)."""
    conn = psycopg2.connect(urls["psycopg2"])
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(LEGACY_FIXTURE.read_text())
    finally:
        conn.close()


def _query(urls: dict[str, str], sql: str) -> list[tuple]:
    conn = psycopg2.connect(urls["psycopg2"])
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()
    finally:
        conn.close()


def _with_engine(urls: dict[str, str], fn: Callable[[sa.Engine], None]) -> None:
    engine = sa.create_engine(urls["sync"])
    try:
        fn(engine)
    finally:
        engine.dispose()


def _assert_orm_parity(urls: dict[str, str]) -> None:
    """Name-level reflection diff: every ORM-mapped table and column exists.

    Imports the same three model modules alembic/env.py imports — a new model
    module must be added there (and here) or both go blind to it.
    """
    from app.database import Base  # noqa: PLC0415 — deferred: needs env config
    import app.models  # noqa: F401, PLC0415
    import app.planner_models_db  # noqa: F401, PLC0415
    import app.state.models  # noqa: F401, PLC0415

    def check(engine: sa.Engine) -> None:
        insp = sa.inspect(engine)
        db_tables = set(insp.get_table_names())
        missing_tables: list[str] = []
        missing_columns: list[str] = []
        for name, table in Base.metadata.tables.items():
            if name not in db_tables:
                missing_tables.append(name)
                continue
            db_cols = {c["name"] for c in insp.get_columns(name)}
            missing_columns.extend(
                f"{name}.{col.name}" for col in table.columns if col.name not in db_cols
            )
        assert not missing_tables and not missing_columns, (
            f"schema is missing ORM-mapped objects:\n"
            f"  tables:  {sorted(missing_tables)}\n"
            f"  columns: {sorted(missing_columns)}"
        )

    _with_engine(urls, check)


def _table_names(urls: dict[str, str]) -> set[str]:
    return {r[0] for r in _query(
        urls, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    )}


def _alembic_version(urls: dict[str, str]) -> str:
    rows = _query(urls, "SELECT version_num FROM alembic_version")
    assert len(rows) == 1, f"expected exactly one alembic_version row, got {rows}"
    return rows[0][0]


# ────────────────────────────────────────────────────────────────────────────
# Cases
# ────────────────────────────────────────────────────────────────────────────

def test_fresh_db_bootstrap(db_factory) -> None:
    """Case 1 — empty DB: `upgrade head` builds the complete schema."""
    urls = db_factory("fresh")
    _assert_upgrade_ok(_alembic(urls, "upgrade", "head"))

    _assert_orm_parity(urls)

    extensions = {r[0] for r in _query(urls, "SELECT extname FROM pg_extension")}
    assert EXPECTED_EXTENSIONS <= extensions, f"missing extensions: {EXPECTED_EXTENSIONS - extensions}"

    functions = {r[0] for r in _query(
        urls,
        "SELECT proname FROM pg_proc WHERE proname IN "
        "('memory_temporal_score', 'update_updated_at_column')",
    )}
    assert functions == EXPECTED_FUNCTIONS, f"missing functions: {EXPECTED_FUNCTIONS - functions}"

    assert RESEARCH_TABLES <= _table_names(urls)

    plan_names = {r[0] for r in _query(urls, "SELECT name FROM subscription_plans")}
    assert plan_names == SEED_PLAN_NAMES
    template_slugs = {r[0] for r in _query(urls, "SELECT slug FROM workflow_templates")}
    assert template_slugs == SEED_TEMPLATE_SLUGS

    heads = _alembic(urls, "heads")
    assert heads.returncode == 0, heads.stderr
    assert _alembic_version(urls) in heads.stdout


def test_upgrade_is_idempotent(db_factory) -> None:
    """Case 2 — a second `upgrade head` on a bootstrapped DB is a clean no-op."""
    urls = db_factory("idem")
    _assert_upgrade_ok(_alembic(urls, "upgrade", "head"))
    version_before = _alembic_version(urls)
    tables_before = _table_names(urls)

    _assert_upgrade_ok(_alembic(urls, "upgrade", "head"))
    assert _alembic_version(urls) == version_before
    assert _table_names(urls) == tables_before


def test_legacy_schema_sql_seeded_db(db_factory) -> None:
    """Case 3 — schema.sql-seeded DB with no alembic history: guarded upgrade,
    ORM-only columns reconciled, seeds not duplicated."""
    urls = db_factory("legacy")
    _apply_legacy_fixture(urls)

    _assert_upgrade_ok(_alembic(urls, "upgrade", "head"))

    _assert_orm_parity(urls)
    # The 2026-07-11 incident column, explicitly (also covered by parity above).
    cols = {r[0] for r in _query(
        urls,
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'founder_profiles'",
    )}
    assert "primary_goal_description" in cols

    (count,) = _query(urls, "SELECT count(*) FROM subscription_plans")[0]
    assert count == 4, f"seeds duplicated: {count} subscription_plans rows"


def test_stamped_at_head_is_noop(db_factory) -> None:
    """Case 4 — prod shape: DB stamped at head executes zero migrations, and the
    re-rooted chain still has exactly one head."""
    urls = db_factory("stamped")
    _apply_legacy_fixture(urls)
    _assert_upgrade_ok(_alembic(urls, "stamp", "head"))
    version_before = _alembic_version(urls)

    result = _alembic(urls, "upgrade", "head")
    _assert_upgrade_ok(result)
    assert "Running upgrade" not in result.stdout + result.stderr
    assert _alembic_version(urls) == version_before

    heads = _alembic(urls, "heads")
    assert heads.returncode == 0, heads.stderr
    head_lines = [line for line in heads.stdout.splitlines() if "(head)" in line]
    assert len(head_lines) == 1, f"expected exactly one head, got: {heads.stdout!r}"
    assert "0002_state_engine" in head_lines[0]
