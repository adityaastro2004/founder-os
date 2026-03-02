"""
Founder OS — Agent API Routes (v2)
====================================
Endpoints for interacting with the enhanced agent system.
Now supports configurable LLM providers, MCP tools, and A2A routing.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ClerkUser, require_auth
from app.config import get_settings
from app.database import get_db
from app.redis import get_redis
from app.agents.registry import AgentRegistry
from app.user_store import get_user as get_planner_user

def _resolve_planner_user_id(clerk_user_id: str) -> str:
    """Resolve the user_store key for a Clerk user.

    The planner routes use a simple string user_id (often 'default-user').
    Try: the Clerk sub directly → 'default-user' fallback.
    This ensures MCP providers can look up Google Calendar tokens.
    """
    # Try the Clerk ID directly
    if get_planner_user(clerk_user_id):
        return clerk_user_id
    # Fallback: most single-user setups use 'default-user'
    if get_planner_user("default-user"):
        return "default-user"
    return clerk_user_id


router = APIRouter(prefix="/api/agents", tags=["agents"])


# ── Request / Response models ─────────────────────────────

class AgentRunRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000, description="User message for the agent")
    session_id: Optional[str] = Field(None, description="Optional session ID for working memory scoping")
    extra_context: Optional[str] = Field(None, description="Additional context to inject into system prompt")


class AgentRunResponse(BaseModel):
    content: str
    agent: str
    model: str
    tokens_used: int
    tool_calls_made: int
    tool_names: list[str] = []
    duration_seconds: float
    stop_reason: str
    cost_usd: float = 0.0
    llm_provider: str = ""
    pending_approvals: list[dict] = []


class AgentInfo(BaseModel):
    name: str
    display_name: str
    description: Optional[str]
    model: str
    available_tools: Optional[list]


class SystemInfo(BaseModel):
    llm_provider: str
    llm_model: str
    agents_registered: list[str]
    event_bus_running: bool


class OrchestrationResponse(BaseModel):
    """Extended response from the orchestrator with delegation trace."""
    content: str
    model: str
    tokens_used: int
    tool_calls_made: int
    tool_names: list[str] = []
    delegations_made: int
    agents_used: list[str]
    duration_seconds: float
    stop_reason: str
    cost_usd: float = 0.0
    llm_provider: str = ""
    pending_approvals: list[dict] = []


# ── Routes ────────────────────────────────────────────────

@router.get("/", response_model=list[AgentInfo])
async def list_agents(
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """List all available agents."""
    settings = get_settings()
    redis = get_redis()
    registry = AgentRegistry(db=db, redis=redis, settings=settings)
    agents = await registry.list_available()
    return agents


@router.get("/system", response_model=SystemInfo)
async def system_info(
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Return agent system configuration info."""
    settings = get_settings()
    redis = get_redis()
    registry = AgentRegistry(db=db, redis=redis, settings=settings)
    return SystemInfo(
        llm_provider=settings.LLM_PROVIDER,
        llm_model=registry._get_model(settings),
        agents_registered=registry.router.registered_agents,
        event_bus_running=registry.event_bus.is_running,
    )


@router.post("/{agent_name}/run", response_model=AgentRunResponse)
async def run_agent(
    agent_name: str,
    body: AgentRunRequest,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a message to an agent and get a response.

    Supports configurable LLM providers (Ollama, Anthropic, OpenAI-compatible).
    The agent will use MCP-compatible tools, memory, and A2A routing.
    """
    settings = get_settings()
    redis = get_redis()
    registry = AgentRegistry(db=db, redis=redis, settings=settings)

    try:
        # user_id from Clerk is a string; derive a deterministic UUID.
        user_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"clerk:{user.user_id}")
        planner_uid = _resolve_planner_user_id(user.user_id)

        agent = await registry.get(
            agent_name,
            user_id=user_uuid,
            session_id=body.session_id,
            planner_user_id=planner_uid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    result = await agent.run(
        body.message,
        extra_context=body.extra_context,
    )

    return AgentRunResponse(
        content=result.content,
        agent=agent_name,
        model=result.model,
        tokens_used=result.tokens_used,
        tool_calls_made=len(result.tool_calls_made),
        tool_names=list({tc.get("tool", "") for tc in result.tool_calls_made if tc.get("tool")}),
        duration_seconds=round(result.duration_seconds, 2),
        stop_reason=result.stop_reason,
        cost_usd=round(result.cost_usd, 6),
        llm_provider=settings.LLM_PROVIDER,
        pending_approvals=result.pending_approvals,
    )


@router.post("/orchestrate", response_model=OrchestrationResponse)
async def orchestrate(
    body: AgentRunRequest,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """
    Primary entry point — send any message to the Orchestrator.

    The orchestrator analyses your request, delegates to the right
    specialist agent(s), and synthesises a coherent response.
    You never need to pick an agent yourself.

    Inspired by Stripe's Minions architecture.
    """
    settings = get_settings()
    redis = get_redis()
    registry = AgentRegistry(db=db, redis=redis, settings=settings)

    user_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"clerk:{user.user_id}")
    planner_uid = _resolve_planner_user_id(user.user_id)

    try:
        agent = await registry.get(
            "orchestrator",
            user_id=user_uuid,
            session_id=body.session_id,
            planner_user_id=planner_uid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    result = await agent.run(
        body.message,
        extra_context=body.extra_context,
    )

    # Extract delegation info from the orchestrator trace
    agents_used = list({d.to_agent for d in result.delegations}) if result.delegations else []

    return OrchestrationResponse(
        content=result.content,
        model=result.model,
        tokens_used=result.tokens_used,
        tool_calls_made=len(result.tool_calls_made),
        tool_names=list({tc.get("tool", "") for tc in result.tool_calls_made if tc.get("tool")}),
        delegations_made=len(result.delegations) if result.delegations else 0,
        agents_used=agents_used,
        duration_seconds=round(result.duration_seconds, 2),
        stop_reason=result.stop_reason,
        cost_usd=round(result.cost_usd, 6),
        llm_provider=settings.LLM_PROVIDER,
        pending_approvals=result.pending_approvals,
    )


# ── SSE helper ────────────────────────────────────────────

def _sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data, default=str)}\n\n"


# ── Streaming orchestrate — SSE with intermediate events ──

@router.post("/orchestrate/stream")
async def orchestrate_stream(
    body: AgentRunRequest,
    request: Request,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """
    Streaming version of /orchestrate.

    Returns Server-Sent Events with intermediate progress events
    (tool calls, delegations) as they happen, followed by a final
    ``done`` event with the full response.

    Event types:
      - started     — agent execution began
      - tool_call   — a tool is being called
      - tool_result — tool call completed
      - thinking    — heartbeat / agent is processing
      - done        — final response with full payload
      - error       — an error occurred
    """
    settings = get_settings()
    redis = get_redis()
    registry = AgentRegistry(db=db, redis=redis, settings=settings)

    user_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"clerk:{user.user_id}")
    planner_uid = _resolve_planner_user_id(user.user_id)

    try:
        agent = await registry.get(
            "orchestrator",
            user_id=user_uuid,
            session_id=body.session_id,
            planner_user_id=planner_uid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    async def event_generator():
        from app.agents.event_bus import Event

        pubsub = redis.pubsub()
        await pubsub.psubscribe("fos:events:tool.*", "fos:events:agent.*")

        yield _sse({"type": "started", "timestamp": time.time()})

        result_future: asyncio.Future = asyncio.get_event_loop().create_future()

        async def _run_agent():
            try:
                res = await agent.run(body.message, extra_context=body.extra_context)
                if not result_future.done():
                    result_future.set_result(res)
            except Exception as exc:
                if not result_future.done():
                    result_future.set_exception(exc)

        task = asyncio.create_task(_run_agent())

        try:
            while not result_future.done():
                if await request.is_disconnected():
                    task.cancel()
                    break

                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)

                if msg and msg.get("data") and not isinstance(msg["data"], int):
                    try:
                        event = Event.from_json(msg["data"])
                        if event.type == "tool.called":
                            yield _sse({
                                "type": "tool_call",
                                "agent": event.agent,
                                "tool_name": event.data.get("tool_name", ""),
                                "timestamp": event.timestamp,
                            })
                        elif event.type == "tool.result":
                            yield _sse({
                                "type": "tool_result",
                                "agent": event.agent,
                                "tool_name": event.data.get("tool_name", ""),
                                "is_error": event.data.get("is_error", False),
                                "duration_ms": event.data.get("duration_ms", 0),
                                "timestamp": event.timestamp,
                            })
                        elif event.type in ("agent.started", "agent.completed"):
                            yield _sse({
                                "type": event.type.replace(".", "_"),
                                "agent": event.agent,
                                "data": event.data,
                                "timestamp": event.timestamp,
                            })
                    except (json.JSONDecodeError, KeyError):
                        pass
                else:
                    yield _sse({"type": "thinking", "timestamp": time.time()})

            # Final result
            if result_future.done() and not result_future.cancelled():
                if result_future.exception():
                    yield _sse({
                        "type": "error",
                        "error": str(result_future.exception()),
                        "timestamp": time.time(),
                    })
                else:
                    result = result_future.result()
                    agents_used = (
                        list({d.to_agent for d in result.delegations})
                        if result.delegations else []
                    )
                    yield _sse({
                        "type": "done",
                        "content": result.content,
                        "model": result.model,
                        "tokens_used": result.tokens_used,
                        "tool_calls_made": len(result.tool_calls_made),
                        "tool_names": list({
                            tc.get("tool", "")
                            for tc in result.tool_calls_made
                            if tc.get("tool")
                        }),
                        "delegations_made": len(result.delegations) if result.delegations else 0,
                        "agents_used": agents_used,
                        "duration_seconds": round(result.duration_seconds, 2),
                        "stop_reason": result.stop_reason,
                        "cost_usd": round(result.cost_usd, 6),
                        "llm_provider": settings.LLM_PROVIDER,
                        "pending_approvals": result.pending_approvals,
                        "timestamp": time.time(),
                    })
        finally:
            await pubsub.punsubscribe()
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
