"""
Founder OS — Celery Application
=================================
Background task queue for long-running agent executions.

Redis is used as both broker and result backend.
Agent HTTP-level retries (api_client.py) remain httpx-based —
Celery handles *task-level* retries for agent runs (LLM timeout,
DB unavailable, transient failures).

Start the worker:
    celery -A app.celery_app worker --loglevel=info -Q default,agents,orchestrator

Start the beat scheduler (optional — for periodic tasks):
    celery -A app.celery_app beat --loglevel=info
"""

from __future__ import annotations

from celery import Celery

from app.config import get_settings

settings = get_settings()

# ── Celery instance ──────────────────────────────────────────
celery = Celery(
    "founder_os",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

# ── Configuration ────────────────────────────────────────────
celery.conf.update(
    # Serialisation — JSON only (safe, debuggable)
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    content_encoding="utf-8",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Result expiry — keep results for 24 hours
    result_expires=86400,

    # Task behaviour
    task_acks_late=True,              # ack after execution (safer)
    worker_prefetch_multiplier=1,     # 1 task at a time per worker process
    task_track_started=True,          # track STARTED state
    task_reject_on_worker_lost=True,  # requeue if worker dies mid-task

    # Default retry policy for all tasks
    task_default_retry_delay=10,      # 10s base delay
    task_max_retries=3,               # up to 3 retries

    # Queues — priority separation
    task_default_queue="default",
    task_queues={
        "default": {"exchange": "default", "routing_key": "default"},
        "agents": {"exchange": "agents", "routing_key": "agents"},
        "orchestrator": {"exchange": "orchestrator", "routing_key": "orchestrator"},
    },

    # Route tasks to the right queue
    task_routes={
        "app.tasks.agent_tasks.run_agent_task": {"queue": "agents"},
        "app.tasks.agent_tasks.run_orchestration_task": {"queue": "orchestrator"},
    },

    # Worker concurrency — agent tasks are I/O-bound
    worker_concurrency=4,

    # Soft/hard time limits per task (seconds)
    task_soft_time_limit=300,   # 5 min soft limit (raises SoftTimeLimitExceeded)
    task_time_limit=360,        # 6 min hard kill
)

# ── Auto-discover tasks ──────────────────────────────────────
celery.autodiscover_tasks(["app.tasks"])
