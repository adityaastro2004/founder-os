"""Migration tier — the LangGraph checkpoint tables land on `alembic upgrade head`.

Self-contained (mirrors tests/migrations/test_schema_baseline.py's harness): a
throwaway DB, `alembic upgrade head` run the way CD runs it, then a table check.

Needs a reachable pgvector Postgres with CREATEDB rights (nothing else). Configure
via MIGRATIONS_ADMIN_DSN (default: postgresql://founder:founder@localhost:5432/postgres).
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path

import psycopg2
import pytest
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.migrations

API_DIR = Path(__file__).resolve().parents[2]  # …/founder-os/apps/api
ADMIN_DSN = os.environ.get(
    "MIGRATIONS_ADMIN_DSN", "postgresql://founder:founder@localhost:5432/postgres"
)

CHECKPOINT_TABLES = {
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
}


def _admin_conn():
    try:
        conn = psycopg2.connect(ADMIN_DSN)
    except psycopg2.OperationalError as exc:
        pytest.fail(
            f"Cannot reach the migrations Postgres at {ADMIN_DSN!r}: {exc}\n"
            "Start one, e.g.: docker compose up -d postgres, or point "
            "MIGRATIONS_ADMIN_DSN at an existing pgvector Postgres."
        )
    conn.autocommit = True
    return conn


def _urls(dbname: str) -> dict[str, str]:
    base = make_url(ADMIN_DSN).set(database=dbname)
    return {
        "async": base.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False),
        "sync": base.set(drivername="postgresql+psycopg2").render_as_string(hide_password=False),
        "psycopg2": base.set(drivername="postgresql").render_as_string(hide_password=False),
    }


@pytest.fixture
def throwaway_db():
    name = f"fos_cp_{secrets.token_hex(4)}"
    conn = _admin_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE "{name}"')
    finally:
        conn.close()
    try:
        yield _urls(name)
    finally:
        conn = _admin_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            conn.close()


def _alembic(urls: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "DATABASE_URL": urls["async"],
        "DATABASE_URL_SYNC": urls["sync"],
        "APP_ENV": "development",
    }
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=API_DIR, env=env, capture_output=True, text=True, timeout=300,
    )


def _tables(urls: dict[str, str]) -> set[str]:
    conn = psycopg2.connect(urls["psycopg2"])
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE tablename LIKE 'checkpoint%'")
            return {r[0] for r in cur.fetchall()}
    finally:
        conn.close()


def test_checkpoint_tables_created_on_upgrade_head(throwaway_db):
    result = _alembic(throwaway_db, "upgrade", "head")
    assert result.returncode == 0, f"alembic failed:\n{result.stdout}\n{result.stderr}"
    assert CHECKPOINT_TABLES.issubset(_tables(throwaway_db))


def test_checkpoint_setup_is_idempotent(throwaway_db):
    assert _alembic(throwaway_db, "upgrade", "head").returncode == 0
    # a second upgrade is a clean no-op (setup() maintains its own version table)
    second = _alembic(throwaway_db, "upgrade", "head")
    assert second.returncode == 0, f"second upgrade failed:\n{second.stdout}\n{second.stderr}"
    assert CHECKPOINT_TABLES.issubset(_tables(throwaway_db))
