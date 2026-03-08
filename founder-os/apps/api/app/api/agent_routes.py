"""
Founder OS — Agent API Routes (v2)
====================================
Endpoints for interacting with the enhanced agent system.
Now supports configurable LLM providers, MCP tools, and A2A routing.
"""

from __future__ import annotations

import asyncio
import json
import logging
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
from app.models import AgentRun, ChatMessage as ChatMessageModel

logger = logging.getLogger(__name__)


# ── Background insight extraction ─────────────────────────

async def _extract_insights_background(
    user_id: str,
    agent_name: str,
    user_message: str,
    agent_response: str,
    session_id: str | None = None,
    run_id: uuid.UUID | None = None,
) -> None:
    """
    Fire-and-forget: extract user insights via lightweight rules (no LLM).
    Every 25 interactions, synthesise the user profile (uses LLM once).
    """
    try:
        from app.agents.profile_intelligence import ProfileIntelligence
        from app.database import async_session

        async with async_session() as db:
            # Rule-based extraction — no LLM needed
            pi = ProfileIntelligence(db, llm_generate=None)
            insights = await pi.extract_insights(
                user_id=user_id,
                agent_name=agent_name,
                user_message=user_message,
                agent_response=agent_response,
                session_id=session_id,
                agent_run_id=run_id,
            )

            if insights:
                logger.info(
                    "Extracted %d insights for user %s from %s",
                    len(insights), user_id[:8], agent_name,
                )

            # Auto-synthesise profile every 25 interactions (LLM call)
            from app.models import UserProfileIntel
            from sqlalchemy import select
            profile = (await db.execute(
                select(UserProfileIntel).where(UserProfileIntel.user_id == user_id)
            )).scalar_one_or_none()
            if profile and (profile.total_interactions or 0) % 25 == 0 and (profile.total_interactions or 0) > 0:
                # Build LLM callable only when synthesis is needed
                from app.agents.llm import LLMMessage, Role
                settings = get_settings()
                redis = get_redis()
                registry = AgentRegistry(db=db, redis=redis, settings=settings)
                llm = registry.llm_provider

                async def _gen(system: str, prompt: str) -> str:
                    msgs = [LLMMessage(role=Role.USER, content=prompt)]
                    resp = await llm.generate(msgs, system=system, max_tokens=4096)
                    return resp.content

                pi_with_llm = ProfileIntelligence(db, _gen)
                await pi_with_llm.synthesise_profile(user_id)
                logger.info("Auto-synthesised profile for user %s", user_id[:8])

    except Exception as exc:
        logger.warning("Background insight extraction failed: %s", exc)

    except Exception as exc:
        logger.warning("Background insight extraction failed: %s", exc)

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
    delegation_details: list[dict] = []
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

    tool_names = list({tc.get("tool", "") for tc in result.tool_calls_made if tc.get("tool")})

    # Persist the run to DB
    try:
        run_record = AgentRun(
            user_id=user.user_id,
            agent_name=agent_name,
            session_id=body.session_id,
            user_message=body.message,
            agent_response=result.content or "",
            model=result.model,
            tokens_used=result.tokens_used,
            cost_usd=result.cost_usd,
            duration_seconds=round(result.duration_seconds, 2),
            stop_reason=result.stop_reason,
            tool_names=tool_names,
            tool_calls_count=len(result.tool_calls_made),
        )
        db.add(run_record)
        await db.commit()
    except Exception:
        await db.rollback()

    # Fire-and-forget insight extraction
    asyncio.create_task(_extract_insights_background(
        user_id=user.user_id,
        agent_name=agent_name,
        user_message=body.message,
        agent_response=result.content or "",
        session_id=body.session_id,
    ))

    return AgentRunResponse(
        content=result.content,
        agent=agent_name,
        model=result.model,
        tokens_used=result.tokens_used,
        tool_calls_made=len(result.tool_calls_made),
        tool_names=tool_names,
        duration_seconds=round(result.duration_seconds, 2),
        stop_reason=result.stop_reason,
        cost_usd=round(result.cost_usd, 6),
        llm_provider=settings.LLM_PROVIDER,
        pending_approvals=result.pending_approvals,
    )


@router.post("/{agent_name}/chat")
async def chat_with_agent(
    agent_name: str,
    body: AgentRunRequest,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """
    Chat with a specific agent.

    Works like /run but also stores the interaction in SharedMemory
    so the orchestrator (and other agents) can see conversation history.
    Returns a ``reply`` field for convenience alongside the full metadata.
    """
    settings = get_settings()
    redis = get_redis()
    registry = AgentRegistry(db=db, redis=redis, settings=settings)

    try:
        user_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"clerk:{user.user_id}")
        planner_uid = _resolve_planner_user_id(user.user_id)
        session_id = body.session_id or f"{agent_name}-chat-{user.user_id}"

        agent = await registry.get(
            agent_name,
            user_id=user_uuid,
            session_id=session_id,
            planner_user_id=planner_uid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    start = time.time()
    result = await agent.run(body.message, extra_context=body.extra_context)
    duration = round(time.time() - start, 2)

    tool_names = list(
        {tc.get("tool", "") for tc in result.tool_calls_made if tc.get("tool")}
    )

    # ── Store in SharedMemory so orchestrator can see it ──
    from app.agents.memory import SharedMemory

    shared = SharedMemory(redis=redis, user_id=user_uuid, session_id=session_id)
    await shared.set(f"last_{agent_name}_output", result.content)
    await shared.set(f"last_{agent_name}_interaction", {
        "user_message": body.message,
        "agent_reply": result.content,
        "tool_names": tool_names,
        "timestamp": time.time(),
    })

    # Also store in a global shared scope so orchestrator picks it up
    global_shared = SharedMemory(redis=redis, user_id=user_uuid, session_id="orchestrator-global")
    await global_shared.set(f"last_{agent_name}_output", result.content)
    await global_shared.set(f"last_{agent_name}_interaction", {
        "user_message": body.message,
        "agent_reply": result.content,
        "tool_names": tool_names,
        "timestamp": time.time(),
    })

    # ── Persist run + chat messages to DB ──
    try:
        run_record = AgentRun(
            user_id=user.user_id,
            agent_name=agent_name,
            session_id=session_id,
            user_message=body.message,
            agent_response=result.content or "",
            model=result.model,
            tokens_used=result.tokens_used,
            cost_usd=result.cost_usd,
            duration_seconds=duration,
            stop_reason=result.stop_reason,
            tool_names=tool_names,
            tool_calls_count=len(result.tool_calls_made),
        )
        db.add(run_record)

        # Save both user and assistant messages
        user_chat_msg = ChatMessageModel(
            user_id=user.user_id,
            session_id=session_id,
            agent_name=agent_name,
            role="user",
            content=body.message,
        )
        db.add(user_chat_msg)

        assistant_chat_msg = ChatMessageModel(
            user_id=user.user_id,
            session_id=session_id,
            agent_name=agent_name,
            role="assistant",
            content=result.content or "",
            model=result.model,
            tokens_used=result.tokens_used,
            duration_seconds=duration,
            tool_names=tool_names,
            status="clarification_needed" if result.stop_reason == "clarification" else "completed",
        )
        db.add(assistant_chat_msg)

        await db.commit()
    except Exception:
        await db.rollback()

    status = "completed"
    if result.stop_reason == "clarification":
        status = "clarification_needed"

    # Fire-and-forget insight extraction
    asyncio.create_task(_extract_insights_background(
        user_id=user.user_id,
        agent_name=agent_name,
        user_message=body.message,
        agent_response=result.content or "",
        session_id=session_id,
    ))

    return {
        "status": status,
        "reply": result.content,
        "content": result.content,
        "agent": agent_name,
        "model": result.model,
        "tokens_used": result.tokens_used,
        "tool_calls_made": len(result.tool_calls_made),
        "tool_names": tool_names,
        "duration_seconds": duration,
        "stop_reason": result.stop_reason,
        "cost_usd": round(result.cost_usd, 6),
        "llm_provider": settings.LLM_PROVIDER,
        "session_id": session_id,
        "pending_approvals": result.pending_approvals,
    }


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
    delegation_details = [
        {
            "agent": d.to_agent,
            "task": d.task[:200],
            "success": d.success,
            "tokens_used": d.tokens_used,
            "duration_seconds": round(d.duration_seconds, 2),
            "error": d.error or None,
        }
        for d in (result.delegations or [])
    ]
    tool_names_orch = list({tc.get("tool", "") for tc in result.tool_calls_made if tc.get("tool")})

    # Persist orchestrator run to DB
    try:
        run_record = AgentRun(
            user_id=user.user_id,
            agent_name="orchestrator",
            session_id=body.session_id,
            user_message=body.message,
            agent_response=result.content or "",
            model=result.model,
            tokens_used=result.tokens_used,
            cost_usd=result.cost_usd,
            duration_seconds=round(result.duration_seconds, 2),
            stop_reason=result.stop_reason,
            tool_names=tool_names_orch,
            tool_calls_count=len(result.tool_calls_made),
            agents_used=agents_used,
            delegations_made=len(result.delegations) if result.delegations else 0,
            delegation_details=delegation_details,
        )
        db.add(run_record)
        # Save chat messages for persistence
        user_cm = ChatMessageModel(
            user_id=user.user_id,
            session_id=body.session_id or "",
            agent_name="orchestrator",
            role="user",
            content=body.message,
        )
        assistant_cm = ChatMessageModel(
            user_id=user.user_id,
            session_id=body.session_id or "",
            agent_name="orchestrator",
            role="assistant",
            content=result.content or "",
            model=result.model,
            tokens_used=result.tokens_used,
            duration_seconds=round(result.duration_seconds, 2),
            tool_names=tool_names_orch,
            agents_used=agents_used,
            delegations_made=len(result.delegations) if result.delegations else 0,
        )
        db.add(user_cm)
        db.add(assistant_cm)
        await db.commit()
    except Exception:
        await db.rollback()

    # Fire-and-forget insight extraction
    asyncio.create_task(_extract_insights_background(
        user_id=user.user_id,
        agent_name="orchestrator",
        user_message=body.message,
        agent_response=result.content or "",
        session_id=body.session_id,
    ))

    return OrchestrationResponse(
        content=result.content,
        model=result.model,
        tokens_used=result.tokens_used,
        tool_calls_made=len(result.tool_calls_made),
        tool_names=tool_names_orch,
        delegations_made=len(result.delegations) if result.delegations else 0,
        agents_used=agents_used,
        delegation_details=delegation_details,
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
        await pubsub.psubscribe(
            "fos:events:tool.*",
            "fos:events:agent.*",
            "fos:events:delegation.*",
            "fos:events:orchestration.*",
        )

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
                        elif event.type == "delegation.starting":
                            yield _sse({
                                "type": "delegation_starting",
                                "agent": event.agent,
                                "target_agent": event.data.get("target_agent", ""),
                                "task_preview": event.data.get("task_preview", ""),
                                "timestamp": event.timestamp,
                            })
                        elif event.type == "delegation.executing":
                            yield _sse({
                                "type": "delegation_executing",
                                "agent": event.agent,
                                "task_preview": event.data.get("task_preview", ""),
                                "attempt": event.data.get("attempt", 1),
                                "timestamp": event.timestamp,
                            })
                        elif event.type == "delegation.completed":
                            yield _sse({
                                "type": "delegation_completed",
                                "agent": event.agent,
                                "success": event.data.get("success", False),
                                "tokens_used": event.data.get("tokens_used", 0),
                                "duration": event.data.get("duration", 0),
                                "result_preview": event.data.get("result_preview", "")[:200],
                                "timestamp": event.timestamp,
                            })
                        elif event.type == "delegation.failed":
                            yield _sse({
                                "type": "delegation_failed",
                                "agent": event.agent,
                                "error": event.data.get("error", ""),
                                "attempts": event.data.get("attempts", 1),
                                "timestamp": event.timestamp,
                            })
                        elif event.type == "delegation.retrying":
                            yield _sse({
                                "type": "delegation_retrying",
                                "agent": event.agent,
                                "attempt": event.data.get("attempt", 2),
                                "reason": event.data.get("reason", ""),
                                "timestamp": event.timestamp,
                            })
                        elif event.type in ("agent.started", "agent.completed"):
                            yield _sse({
                                "type": event.type.replace(".", "_"),
                                "agent": event.agent,
                                "data": event.data,
                                "timestamp": event.timestamp,
                            })
                        elif event.type == "orchestration.started":
                            yield _sse({
                                "type": "orchestration_started",
                                "agent": event.agent,
                                "phase": event.data.get("phase", "starting"),
                                "timestamp": event.timestamp,
                            })
                        elif event.type == "orchestration.completed":
                            yield _sse({
                                "type": "orchestration_completed",
                                "agents_used": event.data.get("agents_used", []),
                                "delegations": event.data.get("delegations", 0),
                                "total_tokens": event.data.get("total_tokens", 0),
                                "retries": event.data.get("retries", 0),
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
                    # Build delegation_details for streaming response
                    _deleg_details = []
                    if result.delegations:
                        for d in result.delegations:
                            _deleg_details.append({
                                "agent": d.to_agent,
                                "task": d.task[:200],
                                "success": d.success,
                                "tokens": d.tokens_used,
                                "duration": round(d.duration_seconds, 2) if d.duration_seconds else None,
                                "error": d.error,
                            })
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
                        "delegation_details": _deleg_details,
                        "duration_seconds": round(result.duration_seconds, 2),
                        "stop_reason": result.stop_reason,
                        "cost_usd": round(result.cost_usd, 6),
                        "llm_provider": settings.LLM_PROVIDER,
                        "pending_approvals": result.pending_approvals,
                        "timestamp": time.time(),
                    })

                    # Persist streaming orchestrator run to DB
                    try:
                        _tool_names = list({
                            tc.get("tool", "")
                            for tc in result.tool_calls_made
                            if tc.get("tool")
                        })
                        run_record = AgentRun(
                            user_id=user.user_id,
                            agent_name="orchestrator",
                            session_id=body.session_id,
                            user_message=body.message,
                            agent_response=result.content or "",
                            model=result.model,
                            tokens_used=result.tokens_used,
                            cost_usd=result.cost_usd,
                            duration_seconds=round(result.duration_seconds, 2),
                            stop_reason=result.stop_reason,
                            tool_names=_tool_names,
                            tool_calls_count=len(result.tool_calls_made),
                            agents_used=agents_used,
                            delegations_made=len(result.delegations) if result.delegations else 0,
                            delegation_details=_deleg_details,
                        )
                        db.add(run_record)
                        # Save chat messages for persistence
                        user_cm = ChatMessageModel(
                            user_id=user.user_id,
                            session_id=body.session_id or "",
                            agent_name="orchestrator",
                            role="user",
                            content=body.message,
                        )
                        assistant_cm = ChatMessageModel(
                            user_id=user.user_id,
                            session_id=body.session_id or "",
                            agent_name="orchestrator",
                            role="assistant",
                            content=result.content or "",
                            model=result.model,
                            tokens_used=result.tokens_used,
                            duration_seconds=round(result.duration_seconds, 2),
                            tool_names=_tool_names,
                            agents_used=agents_used,
                            delegations_made=len(result.delegations) if result.delegations else 0,
                        )
                        db.add(user_cm)
                        db.add(assistant_cm)
                        await db.commit()
                    except Exception:
                        await db.rollback()

                    # Fire-and-forget insight extraction
                    asyncio.create_task(_extract_insights_background(
                        user_id=user.user_id,
                        agent_name="orchestrator",
                        user_message=body.message,
                        agent_response=result.content or "",
                        session_id=body.session_id,
                    ))
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
