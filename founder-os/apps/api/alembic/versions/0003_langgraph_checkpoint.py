"""langgraph checkpoint tables (durable orchestrator)

Revision ID: 0003_langgraph_checkpoint
Revises: 0002_state_engine
Create Date: 2026-07-27

Creates the tables the LangGraph Postgres checkpointer needs
(``checkpoints``, ``checkpoint_blobs``, ``checkpoint_writes``,
``checkpoint_migrations``). LangGraph manages this schema itself via
``PostgresSaver.setup()`` — outside SQLAlchemy models — so per repo rule #8 we run
that setup here, inside a tracked Alembic migration, rather than ad-hoc at runtime.

``setup()`` is idempotent (it maintains its own ``checkpoint_migrations`` version
table), so re-running is safe.
"""

from __future__ import annotations

import logging

from app.config import get_settings

# revision identifiers, used by Alembic.
revision = "0003_langgraph_checkpoint"
down_revision = "0002_state_engine"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def _dsn() -> str:
    return get_settings().DATABASE_URL.replace("+asyncpg", "")


def upgrade() -> None:
    from langgraph.checkpoint.postgres import PostgresSaver

    with PostgresSaver.from_conn_string(_dsn()) as saver:
        saver.setup()
    logger.info("LangGraph checkpoint tables created/verified")


def downgrade() -> None:
    from alembic import op

    for tbl in (
        "checkpoint_writes",
        "checkpoint_blobs",
        "checkpoints",
        "checkpoint_migrations",
    ):
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
