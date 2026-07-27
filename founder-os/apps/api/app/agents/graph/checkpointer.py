"""App-lifetime LangGraph checkpointer (durability substrate).

Owns a single ``AsyncPostgresSaver`` backed by an async connection pool, opened in
the FastAPI lifespan and shared by every orchestration run. The orchestrator falls
back to ``get_checkpointer()`` when no per-instance checkpointer is set, so wiring
it here is enough to make every run durable + resumable.

DDL (the ``checkpoint*`` tables) is owned by the Alembic migration
``0003_langgraph_checkpoint`` (repo rule #8), NOT created here — this module only
opens/points at the pool. If opening fails, the app still runs; orchestration
simply degrades to non-durable (the graph compiles fine without a checkpointer).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_checkpointer: Any | None = None
_pool: Any | None = None


def checkpointer_dsn(settings: Any) -> str:
    """Plain psycopg3 DSN derived from the app's async ``DATABASE_URL``."""
    return settings.DATABASE_URL.replace("+asyncpg", "")


def get_checkpointer() -> Any | None:
    """Return the app-lifetime checkpointer, or None if durability is disabled."""
    return _checkpointer


async def open_checkpointer(settings: Any) -> Any | None:
    """Open the shared checkpointer + pool. Safe to call once at startup.

    Returns the checkpointer on success, or None if it could not be opened (the
    caller should treat None as "durability disabled", not fatal).
    """
    global _checkpointer, _pool
    if _checkpointer is not None:
        return _checkpointer
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg_pool import AsyncConnectionPool

        dsn = checkpointer_dsn(settings)
        # autocommit is required by the checkpointer's write path.
        _pool = AsyncConnectionPool(
            conninfo=dsn,
            max_size=int(getattr(settings, "CHECKPOINTER_POOL_MAX", 10)),
            open=False,
            kwargs={"autocommit": True, "prepare_threshold": 0},
        )
        await _pool.open()
        _checkpointer = AsyncPostgresSaver(_pool)
        logger.info("LangGraph checkpointer opened (durability enabled)")
        return _checkpointer
    except Exception as exc:  # degrade gracefully — never block startup
        logger.warning("Checkpointer unavailable, orchestration runs non-durable: %s", exc)
        _checkpointer = None
        return None


async def close_checkpointer() -> None:
    """Close the pool on shutdown."""
    global _checkpointer, _pool
    if _pool is not None:
        try:
            await _pool.close()
        except Exception as exc:
            logger.warning("Error closing checkpointer pool: %s", exc)
    _checkpointer = None
    _pool = None
