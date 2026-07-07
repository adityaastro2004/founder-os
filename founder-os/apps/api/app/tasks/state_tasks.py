"""Celery task for State Engine syncs (arch §8): always queued, never inline.

Follows the agent_tasks.py shell pattern: sync Celery function, asyncio.run,
own engine/session/redis, cleanup in finally. Redis SET NX lock per source
(released in finally); the route returns 409 while held.
"""
from __future__ import annotations

import asyncio
import logging

from celery import Task

from app.celery_app import celery

logger = logging.getLogger(__name__)

LOCK_TTL_S = 900


def sync_lock_key(source_id: str) -> str:
    return f"state_sync:{source_id}"


async def _run_sync_async(source_id: str, user_id: str, direction: str) -> dict:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    import redis.asyncio as aioredis

    from app.config import get_settings
    from app.state.service import StateService

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_size=2, max_overflow=3)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = session_factory()
    redis_client = aioredis.from_url(settings.REDIS_URL)
    try:
        service = StateService(session, redis_client)
        return await service.run_sync(source_id, user_id, direction)
    finally:
        try:
            await session.close()
        finally:
            await engine.dispose()
            await redis_client.aclose()


@celery.task(
    name="app.tasks.state_tasks.state_sync_task",
    bind=True,
    max_retries=0,          # syncs are idempotent + re-triggerable; no auto-retry storms
    acks_late=True,
    track_started=True,
    soft_time_limit=840,    # < lock TTL so the lock always outlives the task
    time_limit=870,
)
def state_sync_task(self: Task, source_id: str, user_id: str, direction: str = "both") -> dict:
    task_id = self.request.id
    logger.info("[Task %s] state sync start: source=%s direction=%s", task_id, source_id, direction)

    async def _with_lock() -> dict:
        import redis.asyncio as aioredis

        from app.config import get_settings

        redis_client = aioredis.from_url(get_settings().REDIS_URL)
        key = sync_lock_key(source_id)
        try:
            # Protocol (E2E-regression 2026-07-06): the ROUTE serializes triggers
            # with SET NX "queued" before enqueueing; the task then takes OVER the
            # reservation unconditionally (an NX re-take here can never succeed —
            # that bug made every routed sync abort as "already running").
            # Direct invocations (v1.1 watcher) must go through the same
            # reserve-then-enqueue path or accept last-writer-wins.
            await redis_client.set(key, task_id, ex=LOCK_TTL_S)
            return await _run_sync_async(source_id, user_id, direction)
        finally:
            try:
                await redis_client.delete(key)
            finally:
                await redis_client.aclose()

    try:
        report = asyncio.run(_with_lock())
        logger.info("[Task %s] state sync done: %s", task_id, report)
        return {"status": "success", "report": report}
    except Exception as exc:
        logger.exception("[Task %s] state sync failed", task_id)
        return {"status": "error", "error": str(exc)[:2000]}
