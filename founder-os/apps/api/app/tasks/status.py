"""
Founder OS — Task Status Service
====================================
Reads/manages background task status stored in Redis by Celery tasks.

Provides:
  - get_task_status()   — poll a single task
  - list_user_tasks()   — list a user's recent tasks
  - cancel_task()       — revoke a pending/running task
  - cleanup_old_tasks() — garbage collect expired entries
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

TASK_STATUS_PREFIX = "founder_os:task:"
TASK_INDEX_PREFIX = "founder_os:user_tasks:"


class TaskStatusService:
    """Async service for querying Celery task status from Redis."""

    def __init__(self, redis: aioredis.Redis):
        self._redis = redis

    async def get_status(self, task_id: str) -> Optional[dict]:
        """
        Get the current status of a background task.

        Returns:
            Status dict with keys: task_id, status, result, error,
            started_at, completed_at, failed_at, agent_name, task_type.
            Returns None if the task doesn't exist.
        """
        key = f"{TASK_STATUS_PREFIX}{task_id}"
        raw = await self._redis.get(key)
        if raw is None:
            # Task might still be in Celery's pending state (not yet picked up).
            # Check Celery's AsyncResult as a fallback.
            return await self._check_celery_state(task_id)
        return json.loads(raw)

    async def _check_celery_state(self, task_id: str) -> Optional[dict]:
        """
        Fallback: check Celery's own result backend for tasks that haven't
        written to our custom Redis keys yet (e.g. still PENDING).
        """
        from app.celery_app import celery

        result = celery.AsyncResult(task_id)
        state = result.state  # PENDING, STARTED, SUCCESS, FAILURE, RETRY, REVOKED

        if state == "PENDING":
            return {
                "task_id": task_id,
                "status": "pending",
                "result": None,
                "error": None,
            }
        elif state == "STARTED":
            return {
                "task_id": task_id,
                "status": "started",
                "result": None,
                "error": None,
            }
        elif state == "SUCCESS":
            return {
                "task_id": task_id,
                "status": "completed",
                "result": result.result,
                "error": None,
            }
        elif state == "FAILURE":
            return {
                "task_id": task_id,
                "status": "failed",
                "result": None,
                "error": str(result.result),
            }
        elif state == "RETRY":
            return {
                "task_id": task_id,
                "status": "retrying",
                "result": None,
                "error": str(result.result) if result.result else None,
            }
        elif state == "REVOKED":
            return {
                "task_id": task_id,
                "status": "cancelled",
                "result": None,
                "error": "Task was cancelled",
            }

        return None

    async def list_user_tasks(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        """
        List a user's recent background tasks (most recent first).

        Returns a list of task summaries from the user's index.
        For each task, merges in the current status from Redis.
        """
        key = f"{TASK_INDEX_PREFIX}{user_id}"

        # Get entries from sorted set (newest first)
        entries = await self._redis.zrevrange(key, offset, offset + limit - 1)

        tasks = []
        for raw in entries:
            try:
                meta = json.loads(raw)
                task_id = meta.get("task_id")
                if task_id:
                    # Merge current status
                    status = await self.get_status(task_id)
                    if status:
                        meta.update(status)
                tasks.append(meta)
            except (json.JSONDecodeError, TypeError):
                continue

        return tasks

    async def cancel_task(self, task_id: str) -> dict:
        """
        Cancel a pending or running background task.

        Uses Celery's revoke() with terminate=True for running tasks.

        Returns:
            Status dict of the cancelled task.
        """
        from app.celery_app import celery

        # Revoke the task; terminate=True sends SIGTERM if it's running
        celery.control.revoke(task_id, terminate=True, signal="SIGTERM")

        # Update our Redis status
        key = f"{TASK_STATUS_PREFIX}{task_id}"
        status = {
            "task_id": task_id,
            "status": "cancelled",
            "cancelled_at": time.time(),
            "result": None,
            "error": "Cancelled by user",
        }
        await self._redis.set(key, json.dumps(status), ex=86400)

        logger.info(f"Task {task_id} cancelled by user")
        return status

    async def get_task_count(self, user_id: str) -> int:
        """Get total number of tracked tasks for a user."""
        key = f"{TASK_INDEX_PREFIX}{user_id}"
        return await self._redis.zcard(key)
