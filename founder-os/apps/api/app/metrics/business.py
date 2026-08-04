"""
Business aggregates, refreshed periodically from Postgres (ADR-018).

These are the only metrics that are *pulled* rather than incremented at the event
site: counting users or tasks by scanning tables is far cheaper and far less
invasive than instrumenting every write path that could change them.

Runs on APScheduler in the API process every 5 minutes (see ``app/scheduler.py``).
A Grafana Postgres datasource was rejected in ADR-018 — it would mean either
exposing Postgres to the internet or running a private-connector agent.

Deliberately aggregate-only. Nothing here is broken down per user: metrics leave
the box to a third party, and per-user product analysis is PostHog's job.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.metrics.registry import (
    business_refresh_failures_total,
    integration_sync_age_seconds,
    state_entities,
    tasks_by_status,
    users_active_7d,
    users_total,
)

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_SECONDS = 300


async def collect_business_metrics() -> None:
    """Refresh every business gauge. Safe to call concurrently; idempotent.

    Never raises — this runs on a scheduler thread, and a failed metrics refresh
    must not take down the job or the app. Failures are counted so a permanently
    broken refresh is itself visible on the dashboard.
    """
    from app.database import async_session
    from app.models import Integration, Task, User
    from app.state.models import CompanyStateEntity

    try:
        async with async_session() as session:
            # ── Users ──
            total = await session.scalar(
                select(func.count()).select_from(User).where(User.deleted_at.is_(None))
            )
            users_total.set(total or 0)

            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            active = await session.scalar(
                select(func.count())
                .select_from(User)
                .where(User.deleted_at.is_(None), User.last_login_at >= cutoff)
            )
            users_active_7d.set(active or 0)

            # ── Tasks by status ──
            # clear() first: a status that stops occurring must drop out rather
            # than freeze at its last value forever.
            rows = (
                await session.execute(
                    select(Task.status, func.count()).group_by(Task.status)
                )
            ).all()
            tasks_by_status.clear()
            for status, count in rows:
                tasks_by_status.labels(status=status or "unknown").set(count)

            # ── Company State Engine entities ──
            rows = (
                await session.execute(
                    select(CompanyStateEntity.entity_type, func.count())
                    .where(CompanyStateEntity.is_active.is_(True))
                    .group_by(CompanyStateEntity.entity_type)
                )
            ).all()
            state_entities.clear()
            for entity_type, count in rows:
                state_entities.labels(entity_type=entity_type or "unknown").set(count)

            # ── Integration freshness ──
            # Most recent sync per integration type, across all users. A climbing
            # age is the signal that an adapter has silently stalled.
            rows = (
                await session.execute(
                    select(
                        Integration.integration_type,
                        func.max(Integration.last_sync_at),
                    )
                    .where(Integration.is_active.is_(True))
                    .group_by(Integration.integration_type)
                )
            ).all()
            integration_sync_age_seconds.clear()
            now = datetime.now(timezone.utc)
            for integration_type, last_sync in rows:
                if last_sync is None:
                    continue
                if last_sync.tzinfo is None:
                    last_sync = last_sync.replace(tzinfo=timezone.utc)
                integration_sync_age_seconds.labels(
                    integration_type=integration_type or "unknown"
                ).set((now - last_sync).total_seconds())
    except Exception:
        business_refresh_failures_total.inc()
        logger.warning("Business metrics refresh failed", exc_info=True)
