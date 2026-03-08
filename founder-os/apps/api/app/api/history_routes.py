"""
Founder OS — History & Chat Persistence Routes
================================================
Endpoints for agent run history and persistent chat messages.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ClerkUser, require_auth
from app.database import get_db
from app.models import AgentRun, ChatMessage

router = APIRouter(prefix="/api/history", tags=["history"])


# ── Request / Response models ─────────────────────────

class AgentRunOut(BaseModel):
    id: str
    agent_name: str
    session_id: Optional[str] = None
    user_message: str
    agent_response: str
    model: Optional[str] = None
    tokens_used: int = 0
    cost_usd: float = 0.0
    duration_seconds: float = 0.0
    stop_reason: Optional[str] = None
    tool_names: Optional[list] = None
    tool_calls_count: int = 0
    agents_used: Optional[list] = None
    delegations_made: int = 0
    delegation_details: Optional[list] = None
    status: str = "completed"
    created_at: str


class ChatMessageOut(BaseModel):
    id: str
    role: str
    content: str
    agent_name: str
    session_id: str
    model: Optional[str] = None
    tokens_used: Optional[int] = None
    duration_seconds: Optional[float] = None
    tool_names: Optional[list] = None
    agents_used: Optional[list] = None
    delegations_made: Optional[int] = None
    status: str = "completed"
    created_at: str


class ChatMessageIn(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=255)
    agent_name: str = Field(..., min_length=1, max_length=100)
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1)
    model: Optional[str] = None
    tokens_used: Optional[int] = None
    duration_seconds: Optional[float] = None
    tool_names: Optional[list] = None
    agents_used: Optional[list] = None
    delegations_made: Optional[int] = None
    status: str = "completed"


class SaveRunIn(BaseModel):
    agent_name: str = Field(..., min_length=1, max_length=100)
    session_id: Optional[str] = None
    user_message: str = Field(..., min_length=1)
    agent_response: str = Field(..., min_length=1)
    model: Optional[str] = None
    tokens_used: int = 0
    cost_usd: float = 0.0
    duration_seconds: float = 0.0
    stop_reason: Optional[str] = None
    tool_names: Optional[list] = None
    tool_calls_count: int = 0
    agents_used: Optional[list] = None
    delegations_made: int = 0
    delegation_details: Optional[list] = None
    status: str = "completed"


# ── Agent Runs History ────────────────────────────────

@router.get("/runs", response_model=list[AgentRunOut])
async def get_agent_runs(
    agent_name: Optional[str] = Query(None, description="Filter by agent name"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get agent run history for the current user."""
    q = select(AgentRun).where(AgentRun.user_id == user.user_id)
    if agent_name:
        q = q.where(AgentRun.agent_name == agent_name)
    q = q.order_by(desc(AgentRun.created_at)).limit(limit).offset(offset)

    result = await db.execute(q)
    runs = result.scalars().all()

    return [
        AgentRunOut(
            id=str(r.id),
            agent_name=r.agent_name,
            session_id=r.session_id,
            user_message=r.user_message,
            agent_response=r.agent_response,
            model=r.model,
            tokens_used=r.tokens_used or 0,
            cost_usd=float(r.cost_usd or 0),
            duration_seconds=float(r.duration_seconds or 0),
            stop_reason=r.stop_reason,
            tool_names=r.tool_names,
            tool_calls_count=r.tool_calls_count or 0,
            agents_used=r.agents_used,
            delegations_made=r.delegations_made or 0,
            delegation_details=r.delegation_details,
            status=r.status or "completed",
            created_at=r.created_at.isoformat(),
        )
        for r in runs
    ]


@router.get("/runs/{run_id}", response_model=AgentRunOut)
async def get_agent_run(
    run_id: str,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific agent run by ID."""
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run ID")

    result = await db.execute(
        select(AgentRun).where(
            AgentRun.id == run_uuid,
            AgentRun.user_id == user.user_id,
        )
    )
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Run not found")

    return AgentRunOut(
        id=str(r.id),
        agent_name=r.agent_name,
        session_id=r.session_id,
        user_message=r.user_message,
        agent_response=r.agent_response,
        model=r.model,
        tokens_used=r.tokens_used or 0,
        cost_usd=float(r.cost_usd or 0),
        duration_seconds=float(r.duration_seconds or 0),
        stop_reason=r.stop_reason,
        tool_names=r.tool_names,
        tool_calls_count=r.tool_calls_count or 0,
        agents_used=r.agents_used,
        delegations_made=r.delegations_made or 0,
        delegation_details=r.delegation_details,
        status=r.status or "completed",
        created_at=r.created_at.isoformat(),
    )


@router.post("/runs", response_model=AgentRunOut)
async def save_agent_run(
    body: SaveRunIn,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Save an agent run to persistent history."""
    run = AgentRun(
        user_id=user.user_id,
        agent_name=body.agent_name,
        session_id=body.session_id,
        user_message=body.user_message,
        agent_response=body.agent_response,
        model=body.model,
        tokens_used=body.tokens_used,
        cost_usd=body.cost_usd,
        duration_seconds=body.duration_seconds,
        stop_reason=body.stop_reason,
        tool_names=body.tool_names,
        tool_calls_count=body.tool_calls_count,
        agents_used=body.agents_used,
        delegations_made=body.delegations_made,
        delegation_details=body.delegation_details,
        status=body.status,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    return AgentRunOut(
        id=str(run.id),
        agent_name=run.agent_name,
        session_id=run.session_id,
        user_message=run.user_message,
        agent_response=run.agent_response,
        model=run.model,
        tokens_used=run.tokens_used or 0,
        cost_usd=float(run.cost_usd or 0),
        duration_seconds=float(run.duration_seconds or 0),
        stop_reason=run.stop_reason,
        tool_names=run.tool_names,
        tool_calls_count=run.tool_calls_count or 0,
        agents_used=run.agents_used,
        delegations_made=run.delegations_made or 0,
        delegation_details=run.delegation_details,
        status=run.status or "completed",
        created_at=run.created_at.isoformat(),
    )


# ── Chat Messages Persistence ────────────────────────

@router.get("/chat/{session_id}", response_model=list[ChatMessageOut])
async def get_chat_messages(
    session_id: str,
    limit: int = Query(200, ge=1, le=500),
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Load persistent chat messages for a session."""
    result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.user_id == user.user_id,
            ChatMessage.session_id == session_id,
        )
        .order_by(ChatMessage.created_at)
        .limit(limit)
    )
    messages = result.scalars().all()

    return [
        ChatMessageOut(
            id=str(m.id),
            role=m.role,
            content=m.content,
            agent_name=m.agent_name,
            session_id=m.session_id,
            model=m.model,
            tokens_used=m.tokens_used,
            duration_seconds=float(m.duration_seconds) if m.duration_seconds else None,
            tool_names=m.tool_names,
            agents_used=m.agents_used,
            delegations_made=m.delegations_made,
            status=m.status or "completed",
            created_at=m.created_at.isoformat(),
        )
        for m in messages
    ]


@router.post("/chat", response_model=ChatMessageOut)
async def save_chat_message(
    body: ChatMessageIn,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Save a chat message to persistent storage."""
    msg = ChatMessage(
        user_id=user.user_id,
        session_id=body.session_id,
        agent_name=body.agent_name,
        role=body.role,
        content=body.content,
        model=body.model,
        tokens_used=body.tokens_used,
        duration_seconds=body.duration_seconds,
        tool_names=body.tool_names,
        agents_used=body.agents_used,
        delegations_made=body.delegations_made,
        status=body.status,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    return ChatMessageOut(
        id=str(msg.id),
        role=msg.role,
        content=msg.content,
        agent_name=msg.agent_name,
        session_id=msg.session_id,
        model=msg.model,
        tokens_used=msg.tokens_used,
        duration_seconds=float(msg.duration_seconds) if msg.duration_seconds else None,
        tool_names=msg.tool_names,
        agents_used=msg.agents_used,
        delegations_made=msg.delegations_made,
        status=msg.status or "completed",
        created_at=msg.created_at.isoformat(),
    )


@router.post("/chat/batch", response_model=list[ChatMessageOut])
async def save_chat_messages_batch(
    messages: list[ChatMessageIn],
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Save multiple chat messages at once."""
    saved = []
    for body in messages:
        msg = ChatMessage(
            user_id=user.user_id,
            session_id=body.session_id,
            agent_name=body.agent_name,
            role=body.role,
            content=body.content,
            model=body.model,
            tokens_used=body.tokens_used,
            duration_seconds=body.duration_seconds,
            tool_names=body.tool_names,
            agents_used=body.agents_used,
            delegations_made=body.delegations_made,
            status=body.status,
        )
        db.add(msg)
        saved.append(msg)

    await db.commit()
    for msg in saved:
        await db.refresh(msg)

    return [
        ChatMessageOut(
            id=str(msg.id),
            role=msg.role,
            content=msg.content,
            agent_name=msg.agent_name,
            session_id=msg.session_id,
            model=msg.model,
            tokens_used=msg.tokens_used,
            duration_seconds=float(msg.duration_seconds) if msg.duration_seconds else None,
            tool_names=msg.tool_names,
            agents_used=msg.agents_used,
            delegations_made=msg.delegations_made,
            status=msg.status or "completed",
            created_at=msg.created_at.isoformat(),
        )
        for msg in saved
    ]


@router.get("/sessions", response_model=list[dict])
async def list_chat_sessions(
    agent_name: Optional[str] = Query(None),
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """List distinct chat sessions for the user, with last message preview."""
    q = (
        select(
            ChatMessage.session_id,
            ChatMessage.agent_name,
            func.max(ChatMessage.created_at).label("last_message_at"),
            func.count(ChatMessage.id).label("message_count"),
        )
        .where(ChatMessage.user_id == user.user_id)
        .group_by(ChatMessage.session_id, ChatMessage.agent_name)
        .order_by(desc(func.max(ChatMessage.created_at)))
    )
    if agent_name:
        q = q.where(ChatMessage.agent_name == agent_name)

    result = await db.execute(q)
    rows = result.all()

    return [
        {
            "session_id": row.session_id,
            "agent_name": row.agent_name,
            "last_message_at": row.last_message_at.isoformat(),
            "message_count": row.message_count,
        }
        for row in rows
    ]
