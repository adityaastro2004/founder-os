"""
Founder OS — User Context & Token Store (PostgreSQL-backed)
=============================================================
Persistent store for user onboarding data, business context,
and Google Calendar tokens.

All data survives server restarts — no more re-auth.

The Pydantic UserProfile is kept as the in-process DTO that routes
and scheduler work with. Under the hood, a PlannerUser row in
PostgreSQL holds the data. On every save_user() the row is upserted;
on every get_user() the row is fetched.

A small write-through cache avoids a DB round-trip on every check,
but the DB is always the source of truth.
"""

from __future__ import annotations

import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field
from app.log_sanitize import sl

logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic DTO (used by routes, scheduler, etc.)
# ============================================================================

class UserProfile(BaseModel):
    """Everything we know about a founder."""
    user_id: str = Field(default_factory=lambda: f"user-{uuid.uuid4().hex[:8]}")
    name: str = ""

    # Business basics
    business_name: str = ""
    business_type: str = ""
    business_stage: str = ""
    industry: str = ""
    target_audience: str = ""
    team_size: int = 1

    # Metrics
    current_mrr: float = 0.0
    current_users: int = 0
    mrr_growth_pct: float = 0.0

    # Weekly planning inputs
    primary_goal: str = ""
    goals_this_week: list[str] = Field(default_factory=list)
    completed_last_week: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    custom_instructions: str = ""

    # Preferences
    timezone: str = "Asia/Kolkata"
    preferred_work_hours: str = "09:00-18:00"
    calendar_id: str = "primary"

    # Google Calendar
    gcal_connected: bool = False
    gcal_tokens: dict[str, Any] = Field(default_factory=dict)

    # Metadata
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_plan_at: str | None = None
    last_plan_events: int = 0
    plan_count: int = 0

    def store_gcal_tokens(self, tokens: dict[str, Any]) -> None:
        tokens["stored_at"] = time.time()
        self.gcal_tokens = tokens
        self.gcal_connected = True

    def has_valid_gcal_tokens(self) -> bool:
        if not self.gcal_tokens:
            return False
        stored_at = self.gcal_tokens.get("stored_at", 0)
        expires_in = self.gcal_tokens.get("expires_in", 3600)
        refresh_token = self.gcal_tokens.get("refresh_token")
        if time.time() < stored_at + expires_in - 60:
            return True
        return bool(refresh_token)


# ============================================================================
# Write-through cache (DB is truth, cache avoids hot-path round-trips)
# ============================================================================

_cache: dict[str, UserProfile] = {}


# ============================================================================
# DB <-> Pydantic conversion helpers
# ============================================================================

def _row_to_profile(row) -> UserProfile:
    """Convert a PlannerUser DB row to a UserProfile Pydantic model."""
    tokens: dict[str, Any] = {}
    if row.gcal_access_token:
        tokens["access_token"] = row.gcal_access_token
    if row.gcal_refresh_token:
        tokens["refresh_token"] = row.gcal_refresh_token
    if row.gcal_token_data:
        tokens.update(row.gcal_token_data)
    if row.gcal_token_expiry:
        stored_at = tokens.get("stored_at", 0)
        if not stored_at and row.gcal_token_data:
            stored_at = row.gcal_token_data.get("stored_at", 0)
        tokens["stored_at"] = stored_at

    return UserProfile(
        user_id=row.user_id,
        name=row.name or "",
        business_name=row.business_name or "",
        business_type=row.business_type or "",
        business_stage=row.business_stage or "",
        industry=row.industry or "",
        target_audience=row.target_audience or "",
        team_size=row.team_size or 1,
        current_mrr=float(row.current_mrr or 0),
        current_users=row.current_users or 0,
        mrr_growth_pct=float(row.mrr_growth_pct or 0),
        primary_goal=row.primary_goal or "",
        goals_this_week=row.goals_this_week or [],
        completed_last_week=row.completed_last_week or [],
        blockers=row.blockers or [],
        custom_instructions=row.custom_instructions or "",
        timezone=row.timezone or "Asia/Kolkata",
        preferred_work_hours=row.preferred_work_hours or "09:00-18:00",
        calendar_id=row.calendar_id or "primary",
        gcal_connected=row.gcal_connected or False,
        gcal_tokens=tokens,
        created_at=row.created_at.isoformat() if row.created_at else datetime.now(timezone.utc).isoformat(),
        last_plan_at=row.last_plan_at.isoformat() if row.last_plan_at else None,
        last_plan_events=row.last_plan_events or 0,
        plan_count=row.plan_count or 0,
    )


def _profile_to_values(user: UserProfile) -> dict[str, Any]:
    """Convert a UserProfile to a dict of column values for upsert."""
    tokens = user.gcal_tokens or {}
    stored_at = tokens.get("stored_at", 0)
    expires_in = tokens.get("expires_in", 3600)

    token_expiry = None
    if stored_at:
        from datetime import datetime as dt, timezone as tz
        token_expiry = dt.fromtimestamp(stored_at + expires_in, tz=tz.utc)

    return {
        "user_id": user.user_id,
        "name": user.name,
        "business_name": user.business_name,
        "business_type": user.business_type,
        "business_stage": user.business_stage,
        "industry": user.industry,
        "target_audience": user.target_audience,
        "team_size": user.team_size,
        "current_mrr": user.current_mrr,
        "current_users": user.current_users,
        "mrr_growth_pct": user.mrr_growth_pct,
        "primary_goal": user.primary_goal,
        "goals_this_week": user.goals_this_week,
        "completed_last_week": user.completed_last_week,
        "blockers": user.blockers,
        "custom_instructions": user.custom_instructions,
        "timezone": user.timezone,
        "preferred_work_hours": user.preferred_work_hours,
        "calendar_id": user.calendar_id,
        "gcal_connected": user.gcal_connected,
        "gcal_access_token": tokens.get("access_token"),
        "gcal_refresh_token": tokens.get("refresh_token"),
        "gcal_token_expiry": token_expiry,
        "gcal_token_data": tokens,
        "plan_count": user.plan_count,
        "last_plan_at": (
            datetime.fromisoformat(user.last_plan_at) if user.last_plan_at else None
        ),
        "last_plan_events": user.last_plan_events,
    }


# ============================================================================
# Public API — same signatures as the old in-memory store
# ============================================================================

def get_user(user_id: str) -> UserProfile | None:
    """Fetch a user. Tries cache first, falls back to sync DB read."""
    if user_id in _cache:
        return _cache[user_id]
    profile = _sync_fetch(user_id)
    if profile:
        _cache[user_id] = profile
    return profile


def get_or_create_user(user_id: str) -> UserProfile:
    """Get an existing user or create a new one."""
    existing = get_user(user_id)
    if existing:
        return existing
    profile = UserProfile(user_id=user_id)
    save_user(profile)
    return profile


def save_user(user: UserProfile) -> None:
    """Persist user to PostgreSQL and update cache."""
    _cache[user.user_id] = user
    _sync_upsert(user)


def list_users() -> list[UserProfile]:
    """List all planner users from DB."""
    return _sync_list_all()


def get_users_with_gcal() -> list[UserProfile]:
    """Return all users with a valid Google Calendar connection."""
    users = _sync_list_gcal_connected()
    return [u for u in users if u.has_valid_gcal_tokens()]


def delete_user(user_id: str) -> bool:
    """Remove a user from DB and cache."""
    _cache.pop(user_id, None)
    return _sync_delete(user_id)


def update_user_context(user_id: str, updates: dict[str, Any]) -> UserProfile:
    """Merge partial updates into a user profile and persist."""
    user = get_or_create_user(user_id)
    for key, value in updates.items():
        if value is not None and hasattr(user, key):
            setattr(user, key, value)
    save_user(user)
    return user


# ============================================================================
# Async variants (for use inside async route handlers)
# ============================================================================

async def async_get_user(user_id: str) -> UserProfile | None:
    """Async version of get_user."""
    if user_id in _cache:
        return _cache[user_id]
    profile = await _async_fetch(user_id)
    if profile:
        _cache[user_id] = profile
    return profile


async def async_save_user(user: UserProfile) -> None:
    """Async version of save_user."""
    _cache[user.user_id] = user
    await _async_upsert(user)


async def async_get_users_with_gcal() -> list[UserProfile]:
    """Async version of get_users_with_gcal."""
    users = await _async_list_gcal_connected()
    return [u for u in users if u.has_valid_gcal_tokens()]


# ============================================================================
# Plan history (now DB-backed)
# ============================================================================

def store_plan_history(
    user_id: str,
    plan_id: str,
    week_of,
    task_count: int,
    events_created: int,
    events_failed: int,
    duration_seconds: float,
    top_priorities: list[str],
    plan_data: dict | None = None,
    gcal_events: list | None = None,
) -> None:
    """Persist a plan record in the plan_history table."""
    _sync_store_plan_history(
        user_id, plan_id, week_of, task_count,
        events_created, events_failed, duration_seconds,
        top_priorities, plan_data, gcal_events,
    )


def get_plan_history(user_id: str, limit: int = 20) -> list[dict]:
    """Retrieve plan history for a user from the DB."""
    return _sync_get_plan_history(user_id, limit)


async def async_store_plan_history(
    user_id: str,
    plan_id: str,
    week_of,
    task_count: int,
    events_created: int,
    events_failed: int,
    duration_seconds: float,
    top_priorities: list[str],
    plan_data: dict | None = None,
    gcal_events: list | None = None,
) -> None:
    """Async persist a plan record."""
    await _async_store_plan_history(
        user_id, plan_id, week_of, task_count,
        events_created, events_failed, duration_seconds,
        top_priorities, plan_data, gcal_events,
    )


async def async_get_plan_history(user_id: str, limit: int = 20) -> list[dict]:
    """Async retrieve plan history."""
    return await _async_get_plan_history(user_id, limit)


# ============================================================================
# Sync DB helpers (using a dedicated sync engine)
# ============================================================================

_sync_engine = None


def _get_sync_engine():
    from sqlalchemy import create_engine
    from app.config import get_settings
    settings = get_settings()
    return create_engine(
        settings.DATABASE_URL_SYNC,
        pool_size=3,
        max_overflow=5,
        pool_pre_ping=True,
    )


def _engine():
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = _get_sync_engine()
    return _sync_engine


def _sync_fetch(user_id: str) -> UserProfile | None:
    from sqlalchemy import text
    try:
        with _engine().connect() as conn:
            row = conn.execute(
                text("SELECT * FROM planner_users WHERE user_id = :uid"),
                {"uid": user_id},
            ).fetchone()
            if row:
                return _row_to_profile(row)
    except Exception as exc:
        logger.error("DB fetch failed for %s: %s", sl(user_id), sl(exc))
    return None


def _sync_upsert(user: UserProfile) -> None:
    from sqlalchemy import text
    vals = _profile_to_values(user)
    try:
        with _engine().begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO planner_users (
                        user_id, name, business_name, business_type, business_stage,
                        industry, target_audience, team_size, current_mrr, current_users,
                        mrr_growth_pct, primary_goal, goals_this_week, completed_last_week,
                        blockers, custom_instructions, timezone, preferred_work_hours,
                        calendar_id, gcal_connected, gcal_access_token, gcal_refresh_token,
                        gcal_token_expiry, gcal_token_data, plan_count, last_plan_at,
                        last_plan_events, updated_at
                    ) VALUES (
                        :user_id, :name, :business_name, :business_type, :business_stage,
                        :industry, :target_audience, :team_size, :current_mrr, :current_users,
                        :mrr_growth_pct, :primary_goal, CAST(:goals_this_week AS jsonb), CAST(:completed_last_week AS jsonb),
                        CAST(:blockers AS jsonb), :custom_instructions, :timezone, :preferred_work_hours,
                        :calendar_id, :gcal_connected, :gcal_access_token, :gcal_refresh_token,
                        :gcal_token_expiry, CAST(:gcal_token_data AS jsonb), :plan_count, :last_plan_at,
                        :last_plan_events, NOW()
                    )
                    ON CONFLICT (user_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        business_name = EXCLUDED.business_name,
                        business_type = EXCLUDED.business_type,
                        business_stage = EXCLUDED.business_stage,
                        industry = EXCLUDED.industry,
                        target_audience = EXCLUDED.target_audience,
                        team_size = EXCLUDED.team_size,
                        current_mrr = EXCLUDED.current_mrr,
                        current_users = EXCLUDED.current_users,
                        mrr_growth_pct = EXCLUDED.mrr_growth_pct,
                        primary_goal = EXCLUDED.primary_goal,
                        goals_this_week = EXCLUDED.goals_this_week,
                        completed_last_week = EXCLUDED.completed_last_week,
                        blockers = EXCLUDED.blockers,
                        custom_instructions = EXCLUDED.custom_instructions,
                        timezone = EXCLUDED.timezone,
                        preferred_work_hours = EXCLUDED.preferred_work_hours,
                        calendar_id = EXCLUDED.calendar_id,
                        gcal_connected = EXCLUDED.gcal_connected,
                        gcal_access_token = EXCLUDED.gcal_access_token,
                        gcal_refresh_token = EXCLUDED.gcal_refresh_token,
                        gcal_token_expiry = EXCLUDED.gcal_token_expiry,
                        gcal_token_data = EXCLUDED.gcal_token_data,
                        plan_count = EXCLUDED.plan_count,
                        last_plan_at = EXCLUDED.last_plan_at,
                        last_plan_events = EXCLUDED.last_plan_events,
                        updated_at = NOW()
                """),
                {
                    **vals,
                    "goals_this_week": _json_dumps(vals["goals_this_week"]),
                    "completed_last_week": _json_dumps(vals["completed_last_week"]),
                    "blockers": _json_dumps(vals["blockers"]),
                    "gcal_token_data": _json_dumps(vals["gcal_token_data"]),
                },
            )
            logger.debug("Upserted planner_user %s", user.user_id)
    except Exception as exc:
        logger.error("DB upsert failed for %s: %s", user.user_id, exc)


def _sync_list_all() -> list[UserProfile]:
    from sqlalchemy import text
    try:
        with _engine().connect() as conn:
            rows = conn.execute(text("SELECT * FROM planner_users ORDER BY created_at")).fetchall()
            return [_row_to_profile(r) for r in rows]
    except Exception as exc:
        logger.error("DB list_all failed: %s", exc)
        return []


def _sync_list_gcal_connected() -> list[UserProfile]:
    from sqlalchemy import text
    try:
        with _engine().connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM planner_users WHERE gcal_connected = TRUE"),
            ).fetchall()
            return [_row_to_profile(r) for r in rows]
    except Exception as exc:
        logger.error("DB list_gcal_connected failed: %s", exc)
        return []


def _sync_delete(user_id: str) -> bool:
    from sqlalchemy import text
    try:
        with _engine().begin() as conn:
            result = conn.execute(
                text("DELETE FROM planner_users WHERE user_id = :uid"),
                {"uid": user_id},
            )
            return result.rowcount > 0
    except Exception as exc:
        logger.error("DB delete failed for %s: %s", user_id, exc)
        return False


def _sync_store_plan_history(
    user_id, plan_id, week_of, task_count,
    events_created, events_failed, duration_seconds,
    top_priorities, plan_data, gcal_events,
) -> None:
    from sqlalchemy import text
    try:
        with _engine().begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO plan_history (
                        user_id, plan_id, week_of, task_count, events_created,
                        events_failed, duration_seconds, top_priorities,
                        plan_data, gcal_events
                    ) VALUES (
                        :user_id, :plan_id, :week_of, :task_count, :events_created,
                        :events_failed, :duration_seconds, CAST(:top_priorities AS jsonb),
                        CAST(:plan_data AS jsonb), CAST(:gcal_events AS jsonb)
                    )
                """),
                {
                    "user_id": user_id,
                    "plan_id": plan_id,
                    "week_of": week_of,
                    "task_count": task_count,
                    "events_created": events_created,
                    "events_failed": events_failed,
                    "duration_seconds": duration_seconds,
                    "top_priorities": _json_dumps(top_priorities),
                    "plan_data": _json_dumps(plan_data or {}),
                    "gcal_events": _json_dumps(gcal_events or []),
                },
            )
    except Exception as exc:
        logger.error("DB store_plan_history failed: %s", exc)


def _sync_get_plan_history(user_id: str, limit: int = 20) -> list[dict]:
    from sqlalchemy import text
    try:
        with _engine().connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT plan_id, week_of, generated_at, task_count,
                           events_created, events_failed, duration_seconds,
                           top_priorities
                    FROM plan_history
                    WHERE user_id = :uid
                    ORDER BY generated_at DESC
                    LIMIT :lim
                """),
                {"uid": user_id, "lim": limit},
            ).fetchall()
            return [
                {
                    "plan_id": r.plan_id,
                    "week_of": r.week_of.isoformat() if r.week_of else None,
                    "generated_at": r.generated_at.isoformat() if r.generated_at else None,
                    "tasks": r.task_count,
                    "events_created": r.events_created,
                    "events_failed": r.events_failed,
                    "duration_seconds": float(r.duration_seconds) if r.duration_seconds else None,
                    "top_priorities": r.top_priorities or [],
                }
                for r in rows
            ]
    except Exception as exc:
        logger.error("DB get_plan_history failed: %s", exc)
        return []


# ============================================================================
# Async DB helpers (using asyncpg via the existing async engine)
# ============================================================================

async def _async_fetch(user_id: str) -> UserProfile | None:
    from sqlalchemy import text as sa_text
    from app.database import async_session
    try:
        async with async_session() as session:
            result = await session.execute(
                sa_text("SELECT * FROM planner_users WHERE user_id = :uid"),
                {"uid": user_id},
            )
            row = result.fetchone()
            if row:
                return _row_to_profile(row)
    except Exception as exc:
        logger.error("Async DB fetch failed for %s: %s", user_id, exc)
    return None


async def _async_upsert(user: UserProfile) -> None:
    from sqlalchemy import text as sa_text
    from app.database import async_session
    vals = _profile_to_values(user)
    try:
        async with async_session() as session:
            await session.execute(
                sa_text("""
                    INSERT INTO planner_users (
                        user_id, name, business_name, business_type, business_stage,
                        industry, target_audience, team_size, current_mrr, current_users,
                        mrr_growth_pct, primary_goal, goals_this_week, completed_last_week,
                        blockers, custom_instructions, timezone, preferred_work_hours,
                        calendar_id, gcal_connected, gcal_access_token, gcal_refresh_token,
                        gcal_token_expiry, gcal_token_data, plan_count, last_plan_at,
                        last_plan_events, updated_at
                    ) VALUES (
                        :user_id, :name, :business_name, :business_type, :business_stage,
                        :industry, :target_audience, :team_size, :current_mrr, :current_users,
                        :mrr_growth_pct, :primary_goal, CAST(:goals_this_week AS jsonb), CAST(:completed_last_week AS jsonb),
                        CAST(:blockers AS jsonb), :custom_instructions, :timezone, :preferred_work_hours,
                        :calendar_id, :gcal_connected, :gcal_access_token, :gcal_refresh_token,
                        :gcal_token_expiry, CAST(:gcal_token_data AS jsonb), :plan_count, :last_plan_at,
                        :last_plan_events, NOW()
                    )
                    ON CONFLICT (user_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        business_name = EXCLUDED.business_name,
                        business_type = EXCLUDED.business_type,
                        business_stage = EXCLUDED.business_stage,
                        industry = EXCLUDED.industry,
                        target_audience = EXCLUDED.target_audience,
                        team_size = EXCLUDED.team_size,
                        current_mrr = EXCLUDED.current_mrr,
                        current_users = EXCLUDED.current_users,
                        mrr_growth_pct = EXCLUDED.mrr_growth_pct,
                        primary_goal = EXCLUDED.primary_goal,
                        goals_this_week = EXCLUDED.goals_this_week,
                        completed_last_week = EXCLUDED.completed_last_week,
                        blockers = EXCLUDED.blockers,
                        custom_instructions = EXCLUDED.custom_instructions,
                        timezone = EXCLUDED.timezone,
                        preferred_work_hours = EXCLUDED.preferred_work_hours,
                        calendar_id = EXCLUDED.calendar_id,
                        gcal_connected = EXCLUDED.gcal_connected,
                        gcal_access_token = EXCLUDED.gcal_access_token,
                        gcal_refresh_token = EXCLUDED.gcal_refresh_token,
                        gcal_token_expiry = EXCLUDED.gcal_token_expiry,
                        gcal_token_data = EXCLUDED.gcal_token_data,
                        plan_count = EXCLUDED.plan_count,
                        last_plan_at = EXCLUDED.last_plan_at,
                        last_plan_events = EXCLUDED.last_plan_events,
                        updated_at = NOW()
                """),
                {
                    **vals,
                    "goals_this_week": _json_dumps(vals["goals_this_week"]),
                    "completed_last_week": _json_dumps(vals["completed_last_week"]),
                    "blockers": _json_dumps(vals["blockers"]),
                    "gcal_token_data": _json_dumps(vals["gcal_token_data"]),
                },
            )
            await session.commit()
    except Exception as exc:
        logger.error("Async DB upsert failed for %s: %s", user.user_id, exc)


async def _async_list_gcal_connected() -> list[UserProfile]:
    from sqlalchemy import text as sa_text
    from app.database import async_session
    try:
        async with async_session() as session:
            result = await session.execute(
                sa_text("SELECT * FROM planner_users WHERE gcal_connected = TRUE"),
            )
            rows = result.fetchall()
            return [_row_to_profile(r) for r in rows]
    except Exception as exc:
        logger.error("Async list_gcal_connected failed: %s", exc)
        return []


async def _async_store_plan_history(
    user_id, plan_id, week_of, task_count,
    events_created, events_failed, duration_seconds,
    top_priorities, plan_data, gcal_events,
) -> None:
    from sqlalchemy import text as sa_text
    from app.database import async_session
    try:
        async with async_session() as session:
            await session.execute(
                sa_text("""
                    INSERT INTO plan_history (
                        user_id, plan_id, week_of, task_count, events_created,
                        events_failed, duration_seconds, top_priorities,
                        plan_data, gcal_events
                    ) VALUES (
                        :user_id, :plan_id, :week_of, :task_count, :events_created,
                        :events_failed, :duration_seconds, CAST(:top_priorities AS jsonb),
                        CAST(:plan_data AS jsonb), CAST(:gcal_events AS jsonb)
                    )
                """),
                {
                    "user_id": user_id,
                    "plan_id": plan_id,
                    "week_of": week_of,
                    "task_count": task_count,
                    "events_created": events_created,
                    "events_failed": events_failed,
                    "duration_seconds": duration_seconds,
                    "top_priorities": _json_dumps(top_priorities),
                    "plan_data": _json_dumps(plan_data or {}),
                    "gcal_events": _json_dumps(gcal_events or []),
                },
            )
            await session.commit()
    except Exception as exc:
        logger.error("Async store_plan_history failed: %s", exc)


async def _async_get_plan_history(user_id: str, limit: int = 20) -> list[dict]:
    from sqlalchemy import text as sa_text
    from app.database import async_session
    try:
        async with async_session() as session:
            result = await session.execute(
                sa_text("""
                    SELECT plan_id, week_of, generated_at, task_count,
                           events_created, events_failed, duration_seconds,
                           top_priorities
                    FROM plan_history
                    WHERE user_id = :uid
                    ORDER BY generated_at DESC
                    LIMIT :lim
                """),
                {"uid": user_id, "lim": limit},
            )
            rows = result.fetchall()
            return [
                {
                    "plan_id": r.plan_id,
                    "week_of": r.week_of.isoformat() if r.week_of else None,
                    "generated_at": r.generated_at.isoformat() if r.generated_at else None,
                    "tasks": r.task_count,
                    "events_created": r.events_created,
                    "events_failed": r.events_failed,
                    "duration_seconds": float(r.duration_seconds) if r.duration_seconds else None,
                    "top_priorities": r.top_priorities or [],
                }
                for r in rows
            ]
    except Exception as exc:
        logger.error("Async get_plan_history failed: %s", exc)
        return []


# ============================================================================
# Utilities
# ============================================================================

def _json_dumps(obj: Any) -> str:
    """Safely serialize to JSON string for SQL JSONB casts."""
    import json
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, default=str)
