"""
Founder OS — Agent Activity Routes
=====================================
Real-time agent activity feed via Server-Sent Events (SSE)
and a REST endpoint for recent activity history.

Endpoints:
    GET /api/activity/stream    — SSE stream of real-time agent events
    GET /api/activity/recent    — Recent activity log (paginated)
    GET /api/activity/stats     — Agent activity summary stats
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ClerkUser, require_auth
from app.database import get_db
from app.redis import get_redis
from app.models import Agent, Task, AgentAnalytics
from app.agents.event_bus import Event, EventBus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/activity", tags=["activity"])

# Redis key for storing recent activity events per user
_ACTIVITY_KEY = "fos:activity:{user_id}"
_MAX_STORED_EVENTS = 200


# ── Response models ───────────────────────────────────────

class ActivityEvent(BaseModel):
    id: str
    event_type: str
    agent_name: str
    agent_display_name: str = ""
    title: str
    description: str = ""
    status: str = ""  # started | completed | failed | tool_call | delegation
    metadata: dict = {}
    timestamp: float
    correlation_id: str = ""


class ActivityResponse(BaseModel):
    events: list[ActivityEvent]
    total: int
    has_more: bool


class AgentStatusSummary(BaseModel):
    agent_name: str
    display_name: str
    status: str  # idle | running | error
    last_active: Optional[float] = None
    tasks_today: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    avg_duration_seconds: Optional[float] = None


class ActivityStatsResponse(BaseModel):
    agents: list[AgentStatusSummary]
    total_events_today: int
    pending_approvals: int


# ── Helpers ───────────────────────────────────────────────

async def _get_user_id(user: ClerkUser) -> str:
    """Resolve the REAL users.id (string) — the key agents now write events/tasks
    under. Opens its own short-lived session (some endpoints here are Redis-only)."""
    from app.database import async_session
    from app.users import get_or_create_user_id

    async with async_session() as session:
        uid = await get_or_create_user_id(user.user_id, session, email=user.email)
        await session.commit()
    return str(uid)


async def _get_user_aliases(user: ClerkUser) -> set[str]:
    """All ids this user's events may be keyed under: the real users.id (current),
    plus the raw Clerk id and the legacy synthetic uuid5 keys (older events)."""
    return {
        user.user_id,
        await _get_user_id(user),
        str(uuid.uuid5(uuid.NAMESPACE_URL, f"clerk:{user.user_id}")),
        str(uuid.uuid5(uuid.NAMESPACE_URL, f"planner:{user.user_id}")),
    }


def _extract_event_user_ids(data: object) -> set[str]:
    if not isinstance(data, dict):
        return set()

    ids = set()
    for key in ("user_id", "clerk_user_id", "planner_user_id", "owner_user_id"):
        value = data.get(key)
        if isinstance(value, str) and value:
            ids.add(value)

    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        ids.update(_extract_event_user_ids(metadata))

    return ids


def _event_belongs_to_user(event: Event, user_aliases: set[str]) -> bool:
    event_user_ids = _extract_event_user_ids(event.data)
    return bool(event_user_ids and event_user_ids.intersection(user_aliases))


_AGENT_DISPLAY_NAMES = {
    "orchestrator": "Orchestrator",
    "planner": "Planner Agent",
    "content": "Content Agent",
    "research": "Research Agent",
    "ops": "Ops Agent",
    "product": "Product Agent",
    "support": "Support Agent",
}


def _make_activity_event(event: Event) -> dict:
    """Convert an EventBus Event into a storable activity dict."""
    agent = event.agent or "system"
    display = _AGENT_DISPLAY_NAMES.get(agent, agent.title())

    title_map = {
        "agent.started": f"{display} started working",
        "agent.completed": f"{display} completed task",
        "agent.failed": f"{display} encountered an error",
        "tool.called": f"{display} is using a tool",
        "tool.result": f"Tool returned result to {display}",
        "task.created": "New task created",
        "task.completed": "Task completed",
        "delegation.requested": f"{display} delegating to specialist",
        "delegation.completed": "Delegation completed",
        "orchestration.started": "Orchestration started",
        "orchestration.completed": "Orchestration completed",
    }

    status_map = {
        "agent.started": "started",
        "agent.completed": "completed",
        "agent.failed": "failed",
        "tool.called": "tool_call",
        "tool.result": "tool_call",
        "task.created": "started",
        "task.completed": "completed",
        "delegation.requested": "delegation",
        "delegation.completed": "completed",
        "orchestration.started": "started",
        "orchestration.completed": "completed",
    }

    return {
        "id": event.event_id or uuid.uuid4().hex[:12],
        "event_type": event.type,
        "agent_name": agent,
        "agent_display_name": display,
        "title": title_map.get(event.type, f"Agent event: {event.type}"),
        "description": event.data.get("description", event.data.get("message", "")),
        "status": status_map.get(event.type, "info"),
        "metadata": event.data,
        "timestamp": event.timestamp,
        "correlation_id": event.correlation_id,
    }


async def _store_activity_event(redis, user_id: str, activity: dict) -> None:
    """Persist an activity event to the user's Redis list."""
    key = _ACTIVITY_KEY.format(user_id=user_id)
    await redis.lpush(key, json.dumps(activity, default=str))
    await redis.ltrim(key, 0, _MAX_STORED_EVENTS - 1)
    # TTL of 7 days
    await redis.expire(key, 7 * 24 * 3600)


# ── SSE Stream ────────────────────────────────────────────

@router.get("/stream")
async def activity_stream(
    request: Request,
    user: ClerkUser = Depends(require_auth),
):
    """
    Server-Sent Events stream of real-time agent activity.
    
    Connect via EventSource:
        const es = new EventSource('/api/activity/stream', { headers: { Authorization: 'Bearer ...' } });
        es.onmessage = (e) => console.log(JSON.parse(e.data));
    """
    redis = get_redis()
    user_id = await _get_user_id(user)
    user_aliases = await _get_user_aliases(user)

    async def event_generator():
        pubsub = redis.pubsub()
        # Subscribe to all agent event channels
        await pubsub.psubscribe("fos:events:*")
        
        try:
            # Send initial heartbeat
            yield f"data: {json.dumps({'type': 'connected', 'timestamp': time.time()})}\n\n"

            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )

                if message and message.get("data") and not isinstance(message["data"], int):
                    try:
                        event = Event.from_json(message["data"])
                        if not _event_belongs_to_user(event, user_aliases):
                            continue
                        activity = _make_activity_event(event)
                        
                        # Store in Redis for history
                        await _store_activity_event(redis, user_id, activity)
                        
                        yield f"data: {json.dumps(activity, default=str)}\n\n"
                    except (json.JSONDecodeError, KeyError):
                        pass
                else:
                    # Send heartbeat every 15 seconds to keep connection alive
                    yield f": heartbeat\n\n"
                    await asyncio.sleep(1)
        finally:
            await pubsub.punsubscribe("fos:events:*")
            await pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Recent Activity ───────────────────────────────────────

@router.get("/recent", response_model=ActivityResponse)
async def get_recent_activity(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    agent: Optional[str] = Query(default=None, description="Filter by agent name"),
    event_type: Optional[str] = Query(default=None, description="Filter by event type"),
    user: ClerkUser = Depends(require_auth),
):
    """Get recent activity events (from Redis cache)."""
    redis = get_redis()
    user_id = await _get_user_id(user)
    key = _ACTIVITY_KEY.format(user_id=user_id)

    # Get all events then filter (Redis list doesn't support filtering)
    raw_events = await redis.lrange(key, 0, _MAX_STORED_EVENTS - 1)  # type: ignore[misc]
    
    events = []
    for raw in raw_events:
        try:
            evt = json.loads(raw)
            if agent and evt.get("agent_name") != agent:
                continue
            if event_type and evt.get("event_type") != event_type:
                continue
            events.append(evt)
        except json.JSONDecodeError:
            continue

    total = len(events)
    page = events[offset:offset + limit]

    return ActivityResponse(
        events=[ActivityEvent(**e) for e in page],
        total=total,
        has_more=(offset + limit) < total,
    )


# ── Activity Stats ────────────────────────────────────────

@router.get("/stats", response_model=ActivityStatsResponse)
async def get_activity_stats(
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get agent status summaries and activity stats."""
    redis = get_redis()
    user_id = await _get_user_id(user)
    user_uuid = uuid.UUID(user_id)

    # Get all agents
    result = await db.execute(select(Agent).where(Agent.is_active == True))
    agents = result.scalars().all()

    # Get task counts per agent for today
    from datetime import datetime, timezone
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    summaries = []
    for agent in agents:
        # Count today's tasks
        task_count = await db.execute(
            select(func.count(Task.id)).where(
                and_(
                    Task.agent_id == agent.id,
                    Task.user_id == user_uuid,
                    Task.created_at >= today_start,
                )
            )
        )
        total_today = task_count.scalar() or 0

        completed_count = await db.execute(
            select(func.count(Task.id)).where(
                and_(
                    Task.agent_id == agent.id,
                    Task.user_id == user_uuid,
                    Task.created_at >= today_start,
                    Task.status == "completed",
                )
            )
        )
        completed = completed_count.scalar() or 0

        failed_count = await db.execute(
            select(func.count(Task.id)).where(
                and_(
                    Task.agent_id == agent.id,
                    Task.user_id == user_uuid,
                    Task.created_at >= today_start,
                    Task.status == "failed",
                )
            )
        )
        failed = failed_count.scalar() or 0

        # Check if agent is currently running (via Redis flag)
        running_key = f"fos:agent_running:{user_id}:{agent.name}"
        is_running = await redis.exists(running_key)

        # Last active time
        last_active_key = f"fos:agent_last_active:{user_id}:{agent.name}"
        last_active_raw = await redis.get(last_active_key)
        last_active = float(last_active_raw) if last_active_raw else None

        status = "running" if is_running else ("idle" if not failed else "error")

        summaries.append(AgentStatusSummary(
            agent_name=agent.name,
            display_name=agent.display_name,
            status=status,
            last_active=last_active,
            tasks_today=total_today,
            tasks_completed=completed,
            tasks_failed=failed,
        ))

    # Total events today
    activity_key = _ACTIVITY_KEY.format(user_id=user_id)
    total_events = await redis.llen(activity_key)  # type: ignore[misc]

    # Pending approvals count
    from app.agents.approval import ApprovalGate
    gate = ApprovalGate(redis)
    pending = await gate.list_pending(user_id)
    pending_count = len(pending)

    return ActivityStatsResponse(
        agents=summaries,
        total_events_today=total_events,
        pending_approvals=pending_count,
    )
