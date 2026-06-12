"""
Founder OS — Agent Celery Tasks
==================================
Background tasks for running agents and orchestration asynchronously.

These tasks bridge the sync Celery world with the async agent system
by using ``asyncio.run()`` internally. Each task:
  1. Creates its own async DB session + Redis connection
  2. Builds an AgentRegistry
  3. Runs the requested agent
  4. Stores the result in Redis for polling
  5. Closes resources cleanly

Retry policy:
  - Transient failures (LLM timeout, DB hiccup): auto-retry with
    exponential backoff, up to 3 retries.
  - Permanent failures (unknown agent, bad input): fail immediately.

Usage:
    from app.tasks.agent_tasks import run_agent_task

    result = run_agent_task.delay(
        agent_name="planner",
        user_id="clerk_user_123",
        message="Plan next week's priorities",
    )
    task_id = result.id  # immediately returned to the caller
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import traceback
import uuid
from typing import Any, Optional

from celery import Task
from celery.exceptions import MaxRetriesExceededError, SoftTimeLimitExceeded

from app.celery_app import celery

logger = logging.getLogger(__name__)


# ── Async infrastructure helpers ──────────────────────────────

async def _create_async_resources():
    """Create fresh async DB session + Redis connection for a worker task."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    import redis.asyncio as aioredis
    from app.config import get_settings

    settings = get_settings()

    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_size=2,
        max_overflow=3,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = session_factory()

    redis_client = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )

    return engine, session, redis_client, settings


async def _cleanup_async_resources(engine, session, redis_client):
    """Close all async resources after a task completes."""
    try:
        await session.close()
    except Exception:
        pass
    try:
        await engine.dispose()
    except Exception:
        pass
    try:
        await redis_client.aclose()
    except Exception:
        pass


# ── Task status helpers ───────────────────────────────────────

TASK_STATUS_PREFIX = "founder_os:task:"
TASK_STATUS_TTL = 86400  # 24 hours


async def _store_task_status(redis_client, task_id: str, status: dict):
    """Store task status in Redis for API polling."""
    key = f"{TASK_STATUS_PREFIX}{task_id}"
    await redis_client.set(key, json.dumps(status), ex=TASK_STATUS_TTL)


async def _store_task_started(redis_client, task_id: str, agent_name: str, task_type: str):
    """Mark task as started with metadata."""
    await _store_task_status(redis_client, task_id, {
        "task_id": task_id,
        "status": "started",
        "agent_name": agent_name,
        "task_type": task_type,
        "started_at": time.time(),
        "result": None,
        "error": None,
    })


async def _store_task_success(redis_client, task_id: str, result: dict):
    """Mark task as completed with results."""
    await _store_task_status(redis_client, task_id, {
        "task_id": task_id,
        "status": "completed",
        "completed_at": time.time(),
        "result": result,
        "error": None,
    })


async def _store_task_failure(redis_client, task_id: str, error: str, retrying: bool = False):
    """Mark task as failed."""
    await _store_task_status(redis_client, task_id, {
        "task_id": task_id,
        "status": "retrying" if retrying else "failed",
        "failed_at": time.time(),
        "result": None,
        "error": error,
    })


# ── User task index helpers ───────────────────────────────────

TASK_INDEX_PREFIX = "founder_os:user_tasks:"
TASK_INDEX_MAX = 100  # keep last 100 tasks per user


async def _index_task_for_user(redis_client, user_id: str, task_id: str, meta: dict):
    """Add a task to the user's task index (sorted set by timestamp)."""
    key = f"{TASK_INDEX_PREFIX}{user_id}"
    await redis_client.zadd(key, {json.dumps({"task_id": task_id, **meta}): time.time()})
    # Trim old entries
    await redis_client.zremrangebyrank(key, 0, -(TASK_INDEX_MAX + 1))
    await redis_client.expire(key, TASK_STATUS_TTL)


# ── Core async runners ───────────────────────────────────────

async def _run_agent_async(
    task_id: str,
    agent_name: str,
    user_id: str,
    message: str,
    session_id: Optional[str] = None,
    extra_context: Optional[str] = None,
) -> dict:
    """
    The actual async agent execution. Creates its own resources,
    runs the agent, stores result in Redis, and cleans up.
    """
    from app.agents.registry import AgentRegistry

    engine, session, redis_client, settings = await _create_async_resources()

    try:
        # Store started status
        await _store_task_started(redis_client, task_id, agent_name, "agent_run")

        # Index for user
        await _index_task_for_user(redis_client, user_id, task_id, {
            "agent_name": agent_name,
            "task_type": "agent_run",
            "message_preview": message[:100],
        })

        # Build registry and agent
        registry = AgentRegistry(db=session, redis=redis_client, settings=settings)

        from app.users import get_or_create_user_id
        user_uuid = await get_or_create_user_id(user_id, session)
        agent = await registry.get(agent_name, user_id=user_uuid, session_id=session_id)

        # Run the agent
        result = await agent.run(message, extra_context=extra_context)

        # Build response dict
        result_dict = {
            "content": result.content,
            "agent": agent_name,
            "model": result.model,
            "tokens_used": result.tokens_used,
            "tool_calls_made": len(result.tool_calls_made),
            "duration_seconds": round(result.duration_seconds, 2),
            "stop_reason": result.stop_reason,
            "cost_usd": round(result.cost_usd, 6),
            "llm_provider": settings.LLM_PROVIDER,
            "pending_approvals": result.pending_approvals,
        }

        # Store success
        await _store_task_success(redis_client, task_id, result_dict)

        # Commit any DB changes from the agent run
        await session.commit()

        return result_dict

    except Exception:
        await session.rollback()
        raise
    finally:
        await _cleanup_async_resources(engine, session, redis_client)


async def _run_orchestration_async(
    task_id: str,
    user_id: str,
    message: str,
    session_id: Optional[str] = None,
    extra_context: Optional[str] = None,
) -> dict:
    """Async orchestration execution — delegates through the Orchestrator agent."""
    from app.agents.registry import AgentRegistry

    engine, session, redis_client, settings = await _create_async_resources()

    try:
        await _store_task_started(redis_client, task_id, "orchestrator", "orchestration")

        await _index_task_for_user(redis_client, user_id, task_id, {
            "agent_name": "orchestrator",
            "task_type": "orchestration",
            "message_preview": message[:100],
        })

        registry = AgentRegistry(db=session, redis=redis_client, settings=settings)

        from app.users import get_or_create_user_id
        user_uuid = await get_or_create_user_id(user_id, session)
        agent = await registry.get("orchestrator", user_id=user_uuid, session_id=session_id)

        result = await agent.run(message, extra_context=extra_context)

        agents_used = list({d.to_agent for d in result.delegations}) if result.delegations else []

        result_dict = {
            "content": result.content,
            "model": result.model,
            "tokens_used": result.tokens_used,
            "tool_calls_made": len(result.tool_calls_made),
            "delegations_made": len(result.delegations) if result.delegations else 0,
            "agents_used": agents_used,
            "duration_seconds": round(result.duration_seconds, 2),
            "stop_reason": result.stop_reason,
            "cost_usd": round(result.cost_usd, 6),
            "llm_provider": settings.LLM_PROVIDER,
            "pending_approvals": result.pending_approvals,
        }

        await _store_task_success(redis_client, task_id, result_dict)
        await session.commit()

        return result_dict

    except Exception:
        await session.rollback()
        raise
    finally:
        await _cleanup_async_resources(engine, session, redis_client)


# ── Transient error detection ─────────────────────────────────

TRANSIENT_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
    SoftTimeLimitExceeded,
)


def _is_transient(exc: Exception) -> bool:
    """Check if an exception is transient (worth retrying)."""
    if isinstance(exc, TRANSIENT_EXCEPTIONS):
        return True
    # LLM provider errors (timeout, rate limit, server error)
    err_msg = str(exc).lower()
    transient_patterns = [
        "timeout", "timed out", "rate limit", "429",
        "502", "503", "504", "connection", "temporarily",
        "overloaded", "capacity",
    ]
    return any(p in err_msg for p in transient_patterns)


# ── Celery Tasks ──────────────────────────────────────────────

@celery.task(
    name="app.tasks.agent_tasks.run_agent_task",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
    track_started=True,
    soft_time_limit=300,
    time_limit=360,
)
def run_agent_task(
    self: Task,
    agent_name: str,
    user_id: str,
    message: str,
    session_id: Optional[str] = None,
    extra_context: Optional[str] = None,
) -> dict:
    """
    Celery task: run a single agent in the background.

    Args:
        agent_name: Agent slug (e.g. "planner", "content").
        user_id:    Clerk user ID string.
        message:    User message for the agent.
        session_id: Optional session ID for memory scoping.
        extra_context: Additional context to inject.

    Returns:
        Agent result dict (same shape as AgentRunResponse).

    Retries:
        Automatically retries transient failures with exponential backoff.
        Max 3 retries: 10s → 40s → 160s (backoff factor 4).
    """
    task_id = self.request.id
    logger.info(f"[Task {task_id}] Starting agent run: {agent_name}")

    try:
        result = asyncio.run(
            _run_agent_async(
                task_id=task_id,
                agent_name=agent_name,
                user_id=user_id,
                message=message,
                session_id=session_id,
                extra_context=extra_context,
            )
        )
        logger.info(f"[Task {task_id}] Agent run completed: {agent_name}")
        return result

    except SoftTimeLimitExceeded:
        logger.warning(f"[Task {task_id}] Agent run timed out: {agent_name}")
        # Store timeout status
        _store_failure_sync(task_id, user_id, "Task timed out (5 min limit)", retrying=False)
        raise

    except Exception as exc:
        logger.error(f"[Task {task_id}] Agent run failed: {agent_name} — {exc}")

        if _is_transient(exc):
            retry_num = self.request.retries
            backoff = 10 * (4 ** retry_num)  # 10s, 40s, 160s
            logger.info(
                f"[Task {task_id}] Transient error, retrying in {backoff}s "
                f"(attempt {retry_num + 1}/3)"
            )
            _store_failure_sync(task_id, user_id, str(exc), retrying=True)
            try:
                self.retry(exc=exc, countdown=backoff)
            except MaxRetriesExceededError:
                logger.error(f"[Task {task_id}] Max retries exceeded: {agent_name}")
                _store_failure_sync(task_id, user_id, f"Max retries exceeded: {exc}", retrying=False)
                raise

        # Non-transient — fail immediately
        _store_failure_sync(task_id, user_id, str(exc), retrying=False)
        raise


@celery.task(
    name="app.tasks.agent_tasks.run_orchestration_task",
    bind=True,
    max_retries=3,
    default_retry_delay=15,
    acks_late=True,
    track_started=True,
    soft_time_limit=300,
    time_limit=360,
)
def run_orchestration_task(
    self: Task,
    user_id: str,
    message: str,
    session_id: Optional[str] = None,
    extra_context: Optional[str] = None,
) -> dict:
    """
    Celery task: run the Orchestrator agent in the background.

    The orchestrator delegates to specialist agents (Stripe Minions pattern),
    so this may take longer and gets its own dedicated queue.

    Returns:
        Orchestration result dict (same shape as OrchestrationResponse).

    Retries:
        Exponential backoff: 15s → 60s → 240s.
    """
    task_id = self.request.id
    logger.info(f"[Task {task_id}] Starting orchestration")

    try:
        result = asyncio.run(
            _run_orchestration_async(
                task_id=task_id,
                user_id=user_id,
                message=message,
                session_id=session_id,
                extra_context=extra_context,
            )
        )
        logger.info(f"[Task {task_id}] Orchestration completed")
        return result

    except SoftTimeLimitExceeded:
        logger.warning(f"[Task {task_id}] Orchestration timed out")
        _store_failure_sync(task_id, user_id, "Orchestration timed out (5 min limit)", retrying=False)
        raise

    except Exception as exc:
        logger.error(f"[Task {task_id}] Orchestration failed: {exc}")

        if _is_transient(exc):
            retry_num = self.request.retries
            backoff = 15 * (4 ** retry_num)  # 15s, 60s, 240s
            logger.info(
                f"[Task {task_id}] Transient error, retrying in {backoff}s "
                f"(attempt {retry_num + 1}/3)"
            )
            _store_failure_sync(task_id, user_id, str(exc), retrying=True)
            try:
                self.retry(exc=exc, countdown=backoff)
            except MaxRetriesExceededError:
                logger.error(f"[Task {task_id}] Max retries exceeded for orchestration")
                _store_failure_sync(task_id, user_id, f"Max retries exceeded: {exc}", retrying=False)
                raise

        _store_failure_sync(task_id, user_id, str(exc), retrying=False)
        raise


# ── Sync helper for storing failure status from Celery tasks ──

def _store_failure_sync(task_id: str, user_id: str, error: str, retrying: bool):
    """Store failure status from sync Celery context using a fresh event loop."""
    try:
        import redis as sync_redis
        from app.config import get_settings

        settings = get_settings()
        r = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)

        key = f"{TASK_STATUS_PREFIX}{task_id}"
        status = {
            "task_id": task_id,
            "status": "retrying" if retrying else "failed",
            "failed_at": time.time(),
            "result": None,
            "error": error,
        }
        r.set(key, json.dumps(status), ex=TASK_STATUS_TTL)
        r.close()
    except Exception as store_err:
        logger.error(f"Failed to store task failure status: {store_err}")
