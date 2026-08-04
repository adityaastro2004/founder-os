"""
Celery worker metrics, bridged through Redis (ADR-018).

The worker runs as a separate container with prefork concurrency, so it cannot
host an in-process Prometheus registry that the scraper could reach: there is no
HTTP server in it, and four forked children would each hold their own counters.

So the worker only *increments Redis hashes* from task signals, and the API
re-emits them on its ``/metrics`` endpoint. One scrape target, no Pushgateway, no
``PROMETHEUS_MULTIPROC_DIR`` shared-tmpfs dance. Counters living in Redis also
survive a worker restart, which is the correct behaviour for a counter.

``prometheus_client``'s ``collect()`` is a **synchronous** generator, but
``app/redis.py`` exposes an async client only. Hence the two-step split:

    await snapshot_celery_metrics(redis)   # async, in the request handler
    generate_latest(REGISTRY)              # sync, CeleryCollector reads the snapshot

``snapshot_celery_metrics`` writes into a module-level dict that the collector then
reads synchronously. This keeps true counter semantics instead of faking counters
with gauges, and needs no second connection pool.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from prometheus_client.metrics_core import CounterMetricFamily, GaugeMetricFamily, SummaryMetricFamily

logger = logging.getLogger(__name__)

# Redis keys. Namespaced under fos:metrics: so they are trivially greppable and
# cannot collide with Celery's own broker keys.
KEY_TASKS = "fos:metrics:celery:tasks"              # hash: "task|queue|state" -> count
KEY_DURATION_SUM = "fos:metrics:celery:duration_sum"    # hash: task -> seconds
KEY_DURATION_COUNT = "fos:metrics:celery:duration_count"  # hash: task -> count

# Celery's default (Redis broker) stores each queue as a list under its own name.
QUEUE_NAMES = ("default", "agents", "orchestrator")

# Field separator. "|" cannot appear in a Celery task name or queue name.
_SEP = "|"


# ============================================================================
# Snapshot (API side, async)
# ============================================================================

_snapshot: dict[str, Any] = {"tasks": {}, "duration_sum": {}, "duration_count": {}, "queue_depth": {}}


async def snapshot_celery_metrics(redis) -> None:
    """Read the worker's Redis counters into memory for the collector to emit.

    Fails open: if Redis is unreachable the previous snapshot is retained and the
    scrape still succeeds with the rest of the metrics. A metrics endpoint that
    500s during an incident is worse than one that serves slightly stale data.
    """
    global _snapshot
    try:
        tasks = await redis.hgetall(KEY_TASKS)
        duration_sum = await redis.hgetall(KEY_DURATION_SUM)
        duration_count = await redis.hgetall(KEY_DURATION_COUNT)
        queue_depth = {name: await redis.llen(name) for name in QUEUE_NAMES}
        _snapshot = {
            "tasks": tasks or {},
            "duration_sum": duration_sum or {},
            "duration_count": duration_count or {},
            "queue_depth": queue_depth,
        }
    except Exception:
        logger.warning("Celery metrics snapshot failed; serving previous values", exc_info=True)


def _current_snapshot() -> dict[str, Any]:
    return _snapshot


def reset_snapshot() -> None:
    """Test helper — clear the cached snapshot."""
    global _snapshot
    _snapshot = {"tasks": {}, "duration_sum": {}, "duration_count": {}, "queue_depth": {}}


# ============================================================================
# Collector (API side, sync)
# ============================================================================

class CeleryCollector:
    """Emit the snapshotted worker counters as Prometheus families.

    Registered against the app registry at startup. Tolerates a completely empty
    snapshot — the worker may never have started, which is normal in dev and in
    tests, and must not break a scrape.
    """

    def collect(self):
        snap = _current_snapshot()

        tasks = CounterMetricFamily(
            "fos_celery_tasks_total",
            "Celery tasks by task name, queue and terminal state.",
            labels=["task", "queue", "state"],
        )
        for field, value in (snap.get("tasks") or {}).items():
            parts = str(field).split(_SEP)
            if len(parts) != 3:
                continue  # malformed key — skip rather than crash the scrape
            try:
                tasks.add_metric(parts, float(value))
            except (TypeError, ValueError):
                continue
        yield tasks

        durations = SummaryMetricFamily(
            "fos_celery_task_duration_seconds",
            "Celery task execution time in seconds, by task name.",
            labels=["task"],
        )
        sums = snap.get("duration_sum") or {}
        counts = snap.get("duration_count") or {}
        for task_name, total in sums.items():
            try:
                durations.add_metric(
                    [str(task_name)],
                    count_value=float(counts.get(task_name, 0)),
                    sum_value=float(total),
                )
            except (TypeError, ValueError):
                continue
        yield durations

        depth = GaugeMetricFamily(
            "fos_celery_queue_depth",
            "Tasks waiting in each Celery queue.",
            labels=["queue"],
        )
        for queue, value in (snap.get("queue_depth") or {}).items():
            try:
                depth.add_metric([str(queue)], float(value))
            except (TypeError, ValueError):
                continue
        yield depth


# ============================================================================
# Signal handlers (worker side, sync)
# ============================================================================

_sync_redis = None
_start_times: dict[str, float] = {}


def _redis_client():
    """Lazily create a *synchronous* Redis client for the worker process.

    Celery signal handlers are sync, and the worker has no running event loop to
    borrow, so ``app.redis`` (async) is unusable here.
    """
    global _sync_redis
    if _sync_redis is None:
        import redis as sync_redis

        from app.config import get_settings

        _sync_redis = sync_redis.from_url(get_settings().REDIS_URL, decode_responses=True)
    return _sync_redis


def _queue_of(task) -> str:
    try:
        return (task.request.delivery_info or {}).get("routing_key") or "default"
    except Exception:
        return "default"


def _record(task_name: str, queue: str, state: str, duration: float | None) -> None:
    try:
        client = _redis_client()
        pipe = client.pipeline()
        pipe.hincrby(KEY_TASKS, f"{task_name}{_SEP}{queue}{_SEP}{state}", 1)
        if duration is not None:
            pipe.hincrbyfloat(KEY_DURATION_SUM, task_name, duration)
            pipe.hincrby(KEY_DURATION_COUNT, task_name, 1)
        pipe.execute()
    except Exception:
        # Never let instrumentation fail a task.
        logger.debug("Celery metric record failed for %s", task_name, exc_info=True)


def register_worker_signals() -> None:
    """Attach task signal handlers. Called from ``app.celery_app`` at import."""
    from celery.signals import task_failure, task_prerun, task_success

    @task_prerun.connect(weak=False)
    def _on_prerun(task_id=None, task=None, **_kwargs):
        if task_id:
            _start_times[task_id] = time.monotonic()

    @task_success.connect(weak=False)
    def _on_success(sender=None, **_kwargs):
        if sender is None:
            return
        task_id = getattr(sender.request, "id", None)
        started = _start_times.pop(task_id, None) if task_id else None
        duration = (time.monotonic() - started) if started is not None else None
        _record(sender.name, _queue_of(sender), "success", duration)

    @task_failure.connect(weak=False)
    def _on_failure(sender=None, task_id=None, **_kwargs):
        if sender is None:
            return
        started = _start_times.pop(task_id, None) if task_id else None
        duration = (time.monotonic() - started) if started is not None else None
        _record(sender.name, _queue_of(sender), "failure", duration)
