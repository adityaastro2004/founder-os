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

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.auth import ClerkUser, require_auth
from app.config import get_settings
from app.database import async_session, get_db
from app.redis import get_redis
from app.agents.registry import AgentRegistry
from app.user_store import get_user as get_planner_user
from app.users import get_or_create_user_id
from app.models import AgentRun, ChatMessage as ChatMessageModel
from app.log_sanitize import sl
from app.posthog_client import get_posthog

logger = logging.getLogger(__name__)


# ── Session history loader — populates ConversationMemory from DB ──

_MAX_HISTORY_MESSAGES = 50  # match ConversationMemory.max_messages


async def _load_session_history(
    agent: "BaseAgent",
    db: AsyncSession,
    user_id: str,
    session_id: str,
    agent_name: str,
) -> None:
    """
    Load prior ChatMessage rows into the agent's ConversationMemory
    so returning users get full conversational continuity.

    Only loads messages for the same (user_id, session_id, agent_name)
    scope, ordered oldest → newest, capped at _MAX_HISTORY_MESSAGES.
    """
    if not session_id:
        return

    result = await db.execute(
        select(ChatMessageModel)
        .where(
            ChatMessageModel.user_id == user_id,
            ChatMessageModel.session_id == session_id,
            ChatMessageModel.agent_name == agent_name,
        )
        .order_by(ChatMessageModel.created_at.desc())
        .limit(_MAX_HISTORY_MESSAGES)
    )
    rows = list(result.scalars().all())

    if not rows:
        return

    # Reverse so oldest first; add to conversation memory in order
    for msg in reversed(rows):
        if msg.role == "user":
            agent.memory.conversation.add_user(msg.content)
        elif msg.role == "assistant":
            agent.memory.conversation.add_assistant(msg.content)


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
    # Skip trivially short messages — no useful signal to extract
    if not user_message or len(user_message.strip()) < 10:
        return

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
                    len(insights), sl(user_id[:8]), sl(agent_name),
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


# ── Background chat→memory capture (task 020 / ADR-014) ────
# Documented, filterable provenance constants (AC-3): the Curator and the
# State Engine `system` feed filter chat pages on source/page_type;
# metadata.session_id is the same-session recall-exclusion key (AC-11).

_CHAT_MEMORY_MIN_INPUT_CHARS = 10   # mirrors the insights guard
_CHAT_MEMORY_TITLE_CHARS = 100      # user-message excerpt cap (" …" marker)
_CHAT_MEMORY_USER_CHARS = 600       # stored user-side cap (" …" marker)
_CHAT_MEMORY_RESPONSE_CHARS = 1400  # stored assistant-side cap (" …" marker)
_CHAT_MEMORY_PAGE_TYPE = "conversation"
_CHAT_MEMORY_SOURCE = "chat"
_CHAT_MEMORY_CHAPTER = "conversations"


def _excerpt(text: str, cap: int) -> str:
    text = text.strip()
    return text if len(text) <= cap else text[:cap] + " …"


async def _store_chat_memory_background(
    user_id: str,
    agent_name: str,
    user_message: str,
    agent_response: str,
    session_id: str | None = None,
) -> None:
    """
    Fire-and-forget: persist the turn's semantics to memory_pages (ADR-014).

    Embedding only — zero LLM completions; an embedding failure still stores
    the page (NULL embedding). Failures are logged and swallowed — the chat
    response is never blocked. Only the user message and the final assistant
    text are persisted, never tool outputs. Everything else uses async_store
    defaults: importance 0.5, decay 0.001, review_in_days None.
    """
    # Skip trivial turns — nothing worth remembering (AC-2)
    if not user_message or len(user_message.strip()) < _CHAT_MEMORY_MIN_INPUT_CHARS:
        return
    if not agent_response or not agent_response.strip():
        return

    try:
        from app.memory.manager import get_memory_manager

        title = (
            f"Chat ({agent_name}): "
            f"{_excerpt(user_message, _CHAT_MEMORY_TITLE_CHARS)}"
        )
        content = (
            f"User: {_excerpt(user_message, _CHAT_MEMORY_USER_CHARS)}\n\n"
            f"Assistant: {_excerpt(agent_response, _CHAT_MEMORY_RESPONSE_CHARS)}"
        )
        await get_memory_manager().async_store(
            user_id=user_id,
            title=title,
            content=content,
            page_type=_CHAT_MEMORY_PAGE_TYPE,
            source=_CHAT_MEMORY_SOURCE,
            chapter=_CHAT_MEMORY_CHAPTER,
            tags=["chat", agent_name],
            metadata={"session_id": session_id or "", "agent": agent_name},
            is_pinned=False,
            auto_embed=True,
        )
    except Exception as exc:
        logger.warning("Background chat memory store failed: %s", sl(str(exc)))


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
        user_uuid = await get_or_create_user_id(user.user_id, db, email=user.email)
        planner_uid = _resolve_planner_user_id(user.user_id)

        agent = await registry.get(
            agent_name,
            user_id=user_uuid,
            session_id=body.session_id,
            planner_user_id=planner_uid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # Load prior conversation history from DB into agent memory
    if body.session_id:
        await _load_session_history(agent, db, user.user_id, body.session_id, agent_name)

    result = await agent.run(
        body.message,
        extra_context=body.extra_context,
    )

    tool_names = list({tc.get("tool", "") for tc in result.tool_calls_made if tc.get("tool")})

    # Persist the run + chat messages to DB
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

        # Save chat messages for session continuity
        if body.session_id:
            db.add(ChatMessageModel(
                user_id=user.user_id,
                session_id=body.session_id,
                agent_name=agent_name,
                role="user",
                content=body.message,
            ))
            db.add(ChatMessageModel(
                user_id=user.user_id,
                session_id=body.session_id,
                agent_name=agent_name,
                role="assistant",
                content=result.content or "",
                model=result.model,
                tokens_used=result.tokens_used,
                duration_seconds=round(result.duration_seconds, 2),
                tool_names=tool_names,
                status="completed",
            ))

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

    # Fire-and-forget chat→memory capture (ADR-014)
    asyncio.create_task(_store_chat_memory_background(
        user_id=user.user_id,
        agent_name=agent_name,
        user_message=body.message,
        agent_response=result.content or "",
        session_id=body.session_id,
    ))

    ph = get_posthog()
    if ph is not None:
        ph.capture(
            distinct_id=user.user_id,
            event="agent_run_completed",
            properties={
                "agent_name": agent_name,
                "model": result.model,
                "tokens_used": result.tokens_used,
                "tool_calls_count": len(result.tool_calls_made),
                "duration_seconds": round(result.duration_seconds, 2),
                "stop_reason": result.stop_reason,
                "llm_provider": settings.LLM_PROVIDER,
                "has_session": bool(body.session_id),
            },
        )

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
        user_uuid = await get_or_create_user_id(user.user_id, db, email=user.email)
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

    # Load prior conversation history from DB into agent memory
    await _load_session_history(agent, db, user.user_id, session_id, agent_name)

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

    # Fire-and-forget chat→memory capture (ADR-014)
    asyncio.create_task(_store_chat_memory_background(
        user_id=user.user_id,
        agent_name=agent_name,
        user_message=body.message,
        agent_response=result.content or "",
        session_id=session_id,
    ))

    ph = get_posthog()
    if ph is not None:
        ph.capture(
            distinct_id=user.user_id,
            event="agent_chat_completed",
            properties={
                "agent_name": agent_name,
                "model": result.model,
                "tokens_used": result.tokens_used,
                "tool_calls_count": len(result.tool_calls_made),
                "duration_seconds": duration,
                "stop_reason": result.stop_reason,
                "llm_provider": settings.LLM_PROVIDER,
                "clarification_needed": result.stop_reason == "clarification",
            },
        )

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

    user_uuid = await get_or_create_user_id(user.user_id, db, email=user.email)
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

    # Load prior conversation history from DB into agent memory
    orch_session = body.session_id or ""
    if orch_session:
        await _load_session_history(agent, db, user.user_id, orch_session, "orchestrator")

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

    # Fire-and-forget chat→memory capture (ADR-014)
    asyncio.create_task(_store_chat_memory_background(
        user_id=user.user_id,
        agent_name="orchestrator",
        user_message=body.message,
        agent_response=result.content or "",
        session_id=body.session_id,
    ))

    ph = get_posthog()
    if ph is not None:
        ph.capture(
            distinct_id=user.user_id,
            event="orchestration_completed",
            properties={
                "model": result.model,
                "tokens_used": result.tokens_used,
                "delegations_made": len(result.delegations) if result.delegations else 0,
                "agents_used": agents_used,
                "tool_calls_count": len(result.tool_calls_made),
                "duration_seconds": round(result.duration_seconds, 2),
                "stop_reason": result.stop_reason,
                "llm_provider": settings.LLM_PROVIDER,
                "has_session": bool(body.session_id),
            },
        )

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


# Strong refs so in-flight background orchestrations are never GC'd
# (asyncio only keeps weak references to tasks).
_background_runs: set[asyncio.Task] = set()


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

    The run itself executes as a detached background task with its own DB
    session: if the client disconnects (tab switch, navigation, reload) the
    orchestration still finishes and persists to chat history. Agent-creation
    errors surface as an SSE ``error`` event rather than a 503.
    """
    settings = get_settings()
    redis = get_redis()

    user_uuid = await get_or_create_user_id(user.user_id, db, email=user.email)
    planner_uid = _resolve_planner_user_id(user.user_id)
    stream_session = body.session_id or ""

    result_future: asyncio.Future = asyncio.get_event_loop().create_future()
    # Mark any exception as retrieved — the client may disconnect before the
    # run finishes, leaving no consumer to await the future.
    result_future.add_done_callback(
        lambda f: f.exception() if not f.cancelled() else None
    )

    async def _run_and_persist() -> None:
        # The request-scoped session dies when the client disconnects, so the
        # run (and its persistence) must use its own session end to end.
        try:
            async with async_session() as bg_db:
                registry = AgentRegistry(db=bg_db, redis=redis, settings=settings)
                agent = await registry.get(
                    "orchestrator",
                    user_id=user_uuid,
                    session_id=body.session_id,
                    planner_user_id=planner_uid,
                )
                if stream_session:
                    await _load_session_history(
                        agent, bg_db, user.user_id, stream_session, "orchestrator"
                    )

                # Persist the user message up-front (after the history load so
                # it is not double-counted in agent memory) so the conversation
                # survives a page reload while the run is still in flight.
                try:
                    bg_db.add(ChatMessageModel(
                        user_id=user.user_id,
                        session_id=stream_session,
                        agent_name="orchestrator",
                        role="user",
                        content=body.message,
                    ))
                    await bg_db.commit()
                except Exception:
                    await bg_db.rollback()

                result = await agent.run(body.message, extra_context=body.extra_context)

                agents_used = (
                    list({d.to_agent for d in result.delegations})
                    if result.delegations else []
                )
                tool_names = list({
                    tc.get("tool", "")
                    for tc in result.tool_calls_made
                    if tc.get("tool")
                })
                deleg_details = [
                    {
                        "agent": d.to_agent,
                        "task": d.task[:200],
                        "success": d.success,
                        "tokens": d.tokens_used,
                        "duration": round(d.duration_seconds, 2) if d.duration_seconds else None,
                        "error": d.error,
                    }
                    for d in (result.delegations or [])
                ]

                try:
                    bg_db.add(AgentRun(
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
                        tool_names=tool_names,
                        tool_calls_count=len(result.tool_calls_made),
                        agents_used=agents_used,
                        delegations_made=len(result.delegations) if result.delegations else 0,
                        delegation_details=deleg_details,
                    ))
                    bg_db.add(ChatMessageModel(
                        user_id=user.user_id,
                        session_id=stream_session,
                        agent_name="orchestrator",
                        role="assistant",
                        content=result.content or "",
                        model=result.model,
                        tokens_used=result.tokens_used,
                        duration_seconds=round(result.duration_seconds, 2),
                        tool_names=tool_names,
                        agents_used=agents_used,
                        delegations_made=len(result.delegations) if result.delegations else 0,
                    ))
                    await bg_db.commit()
                except Exception:
                    await bg_db.rollback()

            # Fire-and-forget insight extraction
            asyncio.create_task(_extract_insights_background(
                user_id=user.user_id,
                agent_name="orchestrator",
                user_message=body.message,
                agent_response=result.content or "",
                session_id=body.session_id,
            ))

            # Fire-and-forget chat→memory capture (ADR-014)
            asyncio.create_task(_store_chat_memory_background(
                user_id=user.user_id,
                agent_name="orchestrator",
                user_message=body.message,
                agent_response=result.content or "",
                session_id=body.session_id,
            ))

            if not result_future.done():
                result_future.set_result(result)
        except Exception as exc:
            logger.exception("orchestrate/stream background run failed")
            if not result_future.done():
                result_future.set_exception(exc)

    # Subscribe before starting the run so no early events are missed
    pubsub = redis.pubsub()
    await pubsub.psubscribe(
        "fos:events:tool.*",
        "fos:events:agent.*",
        "fos:events:delegation.*",
        "fos:events:orchestration.*",
    )

    run_task = asyncio.create_task(_run_and_persist())
    _background_runs.add(run_task)
    run_task.add_done_callback(_background_runs.discard)

    async def event_generator():
        from app.agents.event_bus import Event

        yield _sse({"type": "started", "timestamp": time.time()})

        heartbeats = 0

        try:
            while not result_future.done():
                if await request.is_disconnected():
                    # Client navigated away or reloaded — stop streaming but
                    # let the background run finish and persist to history.
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
                    # Send periodic heartbeat, not every 500ms
                    heartbeats += 1
                    if heartbeats % 10 == 0:
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


# ── History & Session Endpoints ───────────────────────────

@router.get("/{agent_name}/history")
async def get_agent_history(
    agent_name: str,
    session_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve chat message history for a specific agent.

    Optionally filter by session_id. Returns messages oldest → newest.
    """
    stmt = (
        select(ChatMessageModel)
        .where(
            ChatMessageModel.user_id == user.user_id,
            ChatMessageModel.agent_name == agent_name,
        )
    )
    if session_id:
        stmt = stmt.where(ChatMessageModel.session_id == session_id)
    stmt = stmt.order_by(ChatMessageModel.created_at.asc()).offset(offset).limit(limit)

    result = await db.execute(stmt)
    messages = result.scalars().all()

    return {
        "agent": agent_name,
        "session_id": session_id,
        "count": len(messages),
        "offset": offset,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "model": m.model,
                "tokens_used": m.tokens_used,
                "tool_names": m.tool_names,
                "status": m.status,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@router.get("/history/sessions")
async def list_sessions(
    agent_name: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """
    List distinct session IDs for the current user, with the last message timestamp.
    Optionally filter by agent_name.
    """
    from sqlalchemy import func, distinct

    stmt = (
        select(
            ChatMessageModel.session_id,
            ChatMessageModel.agent_name,
            func.max(ChatMessageModel.created_at).label("last_message_at"),
            func.count(ChatMessageModel.id).label("message_count"),
        )
        .where(ChatMessageModel.user_id == user.user_id)
    )
    if agent_name:
        stmt = stmt.where(ChatMessageModel.agent_name == agent_name)
    stmt = (
        stmt.group_by(ChatMessageModel.session_id, ChatMessageModel.agent_name)
        .order_by(func.max(ChatMessageModel.created_at).desc())
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(stmt)
    rows = result.all()

    return {
        "count": len(rows),
        "offset": offset,
        "sessions": [
            {
                "session_id": r.session_id,
                "agent_name": r.agent_name,
                "last_message_at": r.last_message_at.isoformat() if r.last_message_at else None,
                "message_count": r.message_count,
            }
            for r in rows
        ],
    }


@router.get("/history/runs")
async def list_runs(
    agent_name: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """
    List agent run records for the current user.
    Optionally filter by agent_name and/or session_id.
    """
    stmt = select(AgentRun).where(AgentRun.user_id == user.user_id)
    if agent_name:
        stmt = stmt.where(AgentRun.agent_name == agent_name)
    if session_id:
        stmt = stmt.where(AgentRun.session_id == session_id)
    stmt = stmt.order_by(AgentRun.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(stmt)
    runs = result.scalars().all()

    return {
        "count": len(runs),
        "offset": offset,
        "runs": [
            {
                "id": str(r.id),
                "agent_name": r.agent_name,
                "session_id": r.session_id,
                "user_message": r.user_message[:200],
                "agent_response": r.agent_response[:200],
                "model": r.model,
                "tokens_used": r.tokens_used,
                "cost_usd": float(r.cost_usd) if r.cost_usd else 0,
                "duration_seconds": float(r.duration_seconds) if r.duration_seconds else 0,
                "tool_names": r.tool_names,
                "tool_calls_count": r.tool_calls_count,
                "agents_used": r.agents_used,
                "delegations_made": r.delegations_made,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in runs
        ],
    }
