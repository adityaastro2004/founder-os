"""
Founder OS — Agent Registry (v2)
==================================
Factory that composes the full agent architecture:
  LLMProvider + ToolRegistry + Memory + Router + EventBus + Agent

This is the single entry point for creating ready-to-use agents.

The registry also handles the Orchestrator's special wiring:
  - The ``delegate_task`` tool is bound to the orchestrator instance
  - This enables the Stripe Minions pattern (agents-as-tools)

Usage:
    from app.agents.registry import AgentRegistry

    registry = AgentRegistry(db=session, redis=redis_client, settings=settings)
    agent = await registry.get("orchestrator", user_id=user_id)
    result = await agent.run("Help me plan my product launch")
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agents import AGENT_CLASSES
from app.agents.approval import ApprovalGate
from app.agents.base import AgentConfig, BaseAgent
from app.agents.event_bus import EventBus
from app.agents.llm import LLMProvider, create_llm_provider
from app.agents.memory import (
    AgentMemory,
    ConversationMemory,
    LongTermMemory,
    SharedMemory,
    WorkingMemory,
)
from app.agents.mcp_tools import MCPToolManager, MCPGoogleCalendarProvider
from app.agents.router import AgentCard, AgentRouter
from app.agents.tool_protocol import LocalToolProvider, ToolRegistry
from app.models import Agent as AgentModel, UserAgentConfig
from app.retrieval.embeddings import EmbeddingProvider, create_embedding_provider
from app.retrieval.retriever import ContextRetriever


class AgentRegistry:
    """
    Constructs agent instances by combining:
      - DB-stored config (agents + user_agent_configs tables)
      - Concrete Python subclass (from AGENT_CLASSES)
      - LLM provider (Ollama / Anthropic / OpenAI-compat)
      - Tool registry (local tools + MCP servers)
      - Memory layers (conversation, working, shared, long-term)
      - A2A router + event bus
    """

    def __init__(
        self,
        db: AsyncSession,
        redis: aioredis.Redis,
        settings: Any,  # app.config.Settings
    ) -> None:
        self._db = db
        self._redis = redis
        self._settings = settings

        # Create LLM provider from config
        self._llm = create_llm_provider(
            provider=settings.LLM_PROVIDER,
            api_key=self._get_api_key(settings),
            base_url=self._get_base_url(settings),
            model=self._get_model(settings),
            openai_api_key=getattr(settings, 'OPENAI_API_KEY', ''),
            openai_model=getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini'),
            openai_base_url=getattr(settings, 'OPENAI_BASE_URL', 'https://api.openai.com/v1'),
        )

        # Event bus (shared across agents)
        self._event_bus = EventBus(redis)

        # A2A router (shared across agents)
        self._router = AgentRouter(event_bus=self._event_bus)

        # Human-in-the-loop approval gate
        self._approval_gate = ApprovalGate(redis)

        # MCP tool manager (in-process + external MCP providers)
        self._mcp_manager = MCPToolManager(settings)

        # Planner user-store key — set by get() so delegation factory can use it
        self._planner_user_id: str | None = None

        # Embedding provider for auto-RAG in agent runs
        self._embedder = self._create_embedder(settings, redis)

        # Register agent cards and factories
        for name, cls in AGENT_CLASSES.items():
            card = AgentCard(
                name=name,
                display_name=cls.name or name,
                description=(cls.default_system_prompt or "")[:200],
                capabilities=getattr(cls, "capabilities", []),
                tags=getattr(cls, "tags", []),
            )
            self._router.register_card(card)

            # Register factory so agents can delegate to each other
            async def _factory(
                agent_name: str,
                user_id: Any,
                session_id: str | None = None,
                _self=self,
                planner_user_id: str | None = None,
            ) -> BaseAgent:
                # Use the planner_user_id passed in, or fall back to
                # the one stored on the registry by the top-level get() call.
                p_uid = planner_user_id or _self._planner_user_id
                return await _self.get(
                    agent_name, user_id,
                    session_id=session_id,
                    planner_user_id=p_uid,
                )

            self._router.register_factory(name, _factory)

    # -- Provider config helpers -----------------------------------------

    @staticmethod
    def _get_api_key(settings: Any) -> str:
        if settings.LLM_PROVIDER == "anthropic":
            return settings.ANTHROPIC_API_KEY
        elif settings.LLM_PROVIDER == "openai_compatible":
            return settings.OPENAI_API_KEY
        elif settings.LLM_PROVIDER == "gemini":
            return settings.GEMINI_API_KEY
        return ""  # Ollama doesn't need a key

    @staticmethod
    def _get_base_url(settings: Any) -> str:
        if settings.LLM_PROVIDER == "ollama":
            return settings.OLLAMA_BASE_URL
        elif settings.LLM_PROVIDER == "openai_compatible":
            return settings.OPENAI_BASE_URL
        return ""  # Gemini & Anthropic have hardcoded base URLs

    @staticmethod
    def _get_model(settings: Any) -> str:
        if settings.LLM_PROVIDER == "ollama":
            return settings.OLLAMA_MODEL
        elif settings.LLM_PROVIDER == "anthropic":
            return settings.ANTHROPIC_MODEL
        elif settings.LLM_PROVIDER == "openai_compatible":
            return settings.OPENAI_MODEL
        elif settings.LLM_PROVIDER == "gemini":
            return settings.GEMINI_MODEL
        return ""

    @staticmethod
    def _create_embedder(settings: Any, redis: aioredis.Redis) -> EmbeddingProvider:
        """Create the shared embedding provider for auto-RAG."""
        provider = getattr(settings, "EMBEDDING_PROVIDER", "ollama")
        model = getattr(settings, "EMBEDDING_MODEL", "nomic-embed-text")
        api_key = getattr(settings, "EMBEDDING_API_KEY", "")
        base_url = getattr(settings, "EMBEDDING_BASE_URL", "")

        if provider == "ollama":
            base_url = base_url or getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
        elif provider == "openai":
            api_key = api_key or getattr(settings, "OPENAI_API_KEY", "")
            base_url = base_url or None

        return create_embedding_provider(
            provider=provider,
            api_key=api_key or None,
            base_url=base_url or None,
            model=model,
            redis=redis,
        )

    # -- Public API -------------------------------------------------------

    async def get(
        self,
        agent_name: str,
        user_id: uuid.UUID,
        *,
        session_id: str | None = None,
        planner_user_id: str | None = None,
    ) -> BaseAgent:
        """
        Build and return a fully-initialised agent.

        Args:
            agent_name:       Agent slug (e.g. "planner", "content").
            user_id:          The authenticated user's UUID (for memory/DB).
            session_id:       Optional session identifier for memory scoping.
            planner_user_id:  The user-store key (e.g. "default-user" or Clerk
                              sub) used by planner routes and user_store.
                              Needed so MCP providers can look up gcal tokens.
        """
        # 1. Resolve the Python class
        agent_cls = AGENT_CLASSES.get(agent_name)
        if agent_cls is None:
            raise ValueError(
                f"Unknown agent '{agent_name}'. "
                f"Available: {list(AGENT_CLASSES.keys())}"
            )

        # Store planner_user_id so delegation factory can pick it up
        if planner_user_id:
            self._planner_user_id = planner_user_id

        # 2. Load agent row from DB
        db_agent = await self._load_agent(agent_name)

        # 3. Load per-user config overlay (optional)
        user_config = await self._load_user_config(db_agent.id, user_id)

        # 4. Merge into AgentConfig
        config = AgentConfig(
            name=db_agent.name,
            display_name=db_agent.display_name,
            model=db_agent.model,
            temperature=float(db_agent.temperature),
            max_tokens=db_agent.max_tokens,
            system_prompt=db_agent.system_prompt,
            tool_names=(db_agent.available_tools or agent_cls.default_tools),
            custom_instructions=(
                user_config.custom_instructions if user_config else None
            ),
        )

        # 5. Build tool registry with local tools + MCP providers
        tool_registry = ToolRegistry()
        tool_registry.add_provider(
            LocalToolProvider(allowed_tools=config.tool_names)
        )

        # 5b. Add MCP tool providers (Google Calendar, external servers, etc.)
        #     Use planner_user_id (the user_store key) so MCPToolManager can
        #     look up gcal tokens.  Falls back to the UUID string if not given.
        mcp_uid = planner_user_id or str(user_id)
        try:
            mcp_providers = await self._mcp_manager.get_providers(
                user_id=mcp_uid,
            )
            for mcp_provider in mcp_providers:
                tool_registry.add_provider(mcp_provider)
                logger.info(
                    "Added MCP provider '%s' for agent '%s'",
                    mcp_provider.provider_name,
                    agent_name,
                )
        except Exception:
            logger.exception("Failed to load MCP providers for agent '%s'", agent_name)

        await tool_registry.refresh()

        # 6. Build memory layers
        conversation = ConversationMemory(max_messages=50)
        working = WorkingMemory(
            redis=self._redis,
            user_id=user_id,
            agent_name=agent_name,
            session_id=session_id,
        )
        long_term = LongTermMemory(db=self._db, user_id=user_id)
        shared = SharedMemory(
            redis=self._redis,
            user_id=user_id,
            session_id=session_id,
        )

        # 6b. Build ContextRetriever for hybrid/MMR search
        retriever = ContextRetriever(
            db=self._db,
            embedder=self._embedder,
            user_id=user_id,
        )

        memory = AgentMemory(
            conversation=conversation,
            working=working,
            long_term=long_term,
            shared=shared,
            retriever=retriever,
        )

        # 7. Instantiate with all components
        agent = agent_cls(
            config=config,
            memory=memory,
            llm=self._llm,
            tools=tool_registry,
            router=self._router,
            event_bus=self._event_bus,
            approval_gate=self._approval_gate,
            user_id=str(user_id),
            embedder=self._embedder,
        )

        # Set Clerk user ID for profile intelligence lookups.
        # mcp_uid is the original Clerk ID (or "default-user" fallback),
        # which matches how insights are stored in agent_routes.py.
        agent.clerk_user_id = mcp_uid

        # Store the planner user-store key so PlannerAgent.after_run can
        # push plans to Google Calendar automatically.
        if planner_user_id:
            agent._planner_user_id = planner_user_id

        # 8. Wire the delegate_task tool for the orchestrator.
        #    This is the Stripe Minions pattern: the orchestrator's LLM
        #    sees ``delegate_task`` as a regular tool, but under the hood
        #    it creates a specialist agent and runs it.
        if agent_name == "orchestrator":
            from app.agents.orchestrator import OrchestratorAgent
            if isinstance(agent, OrchestratorAgent):
                _orchestrator = agent
                _uid = user_id
                _sid = session_id

                async def _delegate_task_impl(
                    agent_name: str,
                    task: str,
                    context: str = "",
                ) -> str:
                    return await _orchestrator.execute_delegation(
                        agent_name=agent_name,
                        task=task,
                        context=context,
                        user_id=_uid,
                        session_id=_sid,
                    )

                # Inject the real implementation into the tool registry
                tool_registry.override_tool_impl(
                    "delegate_task", _delegate_task_impl,
                )

                # 8b. Wire recall_last_orchestration with shared memory
                _shared_mem = shared

                async def _recall_last_orchestration_impl() -> str:
                    """Fetch the last orchestration summary from shared memory."""
                    try:
                        last = await _shared_mem.get("last_orchestration")
                        if last:
                            return json.dumps({
                                "last_orchestration": json.loads(last),
                                "note": "Prior conversation context loaded.",
                            })
                        return json.dumps({
                            "last_orchestration": None,
                            "note": "No prior orchestration found (first interaction).",
                        })
                    except Exception as exc:
                        return json.dumps({
                            "last_orchestration": None,
                            "error": str(exc),
                        })

                tool_registry.override_tool_impl(
                    "recall_last_orchestration", _recall_last_orchestration_impl,
                )

                # 8c. Wire list_available_agents with router introspection
                _router_ref = self._router

                async def _list_available_agents_impl() -> str:
                    """List all agents with their live capabilities."""
                    agents_info = []
                    for card in _router_ref.list_cards():
                        if card.name == "orchestrator":
                            continue  # Don't list self
                        agents_info.append({
                            "name": card.name,
                            "display_name": card.display_name,
                            "capabilities": card.capabilities,
                            "tags": card.tags,
                            "description": card.description[:150] if card.description else "",
                        })
                    return json.dumps({
                        "agents": agents_info,
                        "total": len(agents_info),
                    })

                tool_registry.override_tool_impl(
                    "list_available_agents", _list_available_agents_impl,
                )

                # 8d. Wire check_delegation_health with live router state
                async def _check_delegation_health_impl() -> str:
                    """Check if the delegation system is healthy."""
                    registered = _router_ref.registered_agents
                    factories_ok = all(
                        n in _router_ref._agent_factory
                        for n in registered
                    )
                    return json.dumps({
                        "status": "healthy" if factories_ok else "degraded",
                        "agents_registered": registered,
                        "agents_available": len(registered),
                        "router_connected": True,
                        "factories_wired": factories_ok,
                    })

                tool_registry.override_tool_impl(
                    "check_delegation_health", _check_delegation_health_impl,
                )

        # 9. Wire get_user_profile with the real user-store data
        _mcp_uid = mcp_uid
        _settings_ref = self._settings

        async def _get_user_profile_impl() -> str:
            """Return the founder's profile as JSON for agent context."""
            from app.user_store import get_user as _get_user
            user_profile = _get_user(_mcp_uid)
            if not user_profile:
                return json.dumps({"error": "No user profile found. Ask the user for their details."})
            data = user_profile.model_dump(exclude={"gcal_tokens"})
            return json.dumps(data, default=str)

        tool_registry.override_tool_impl("get_user_profile", _get_user_profile_impl)

        # 10. Wire check_calendar_conflicts with real MCP calendar
        async def _check_conflicts_impl(
            start_datetime: str,
            end_datetime: str,
        ) -> str:
            """Check for overlapping events in the given time range."""
            from app.user_store import get_user as _get_user
            from datetime import datetime as _dt, timedelta
            user_profile = _get_user(_mcp_uid)
            if not user_profile or not user_profile.gcal_connected:
                return json.dumps({
                    "conflicts": [],
                    "calendar_connected": False,
                    "note": "Google Calendar not connected — cannot check conflicts.",
                })
            try:
                provider = MCPGoogleCalendarProvider(
                    user_id=_mcp_uid,
                    client_id=_settings_ref.GOOGLE_CLIENT_ID,
                    client_secret=_settings_ref.GOOGLE_CLIENT_SECRET,
                    timezone_str=user_profile.timezone or "Asia/Kolkata",
                    calendar_id=user_profile.calendar_id or "primary",
                )
                # Fetch events around the requested window
                events_result = await provider.call_tool(
                    "gcal_list_events",
                    {"max_results": 50, "time_min": start_datetime},
                )
                import json as _json
                all_events = _json.loads(events_result.content)
                # Filter to those that overlap with the proposed range
                conflicts = []
                for ev in (all_events if isinstance(all_events, list) else []):
                    ev_start = ev.get("start", "")
                    ev_end = ev.get("end", "")
                    # Simple string comparison works for ISO datetimes
                    if ev_start and ev_end:
                        if ev_start < end_datetime and ev_end > start_datetime:
                            conflicts.append({
                                "id": ev.get("id", ""),
                                "summary": ev.get("summary", "(no title)"),
                                "start": ev_start,
                                "end": ev_end,
                            })
                return _json.dumps({
                    "conflicts": conflicts,
                    "has_conflicts": len(conflicts) > 0,
                    "calendar_connected": True,
                    "total_checked": len(all_events) if isinstance(all_events, list) else 0,
                })
            except Exception as exc:
                return json.dumps({"error": str(exc), "conflicts": []})

        tool_registry.override_tool_impl("check_calendar_conflicts", _check_conflicts_impl)

        # 11. Wire search_knowledge tool with real ContextRetriever
        _retriever = retriever

        async def _search_knowledge_impl(
            query: str,
            category: str = "",
            limit: int = 5,
        ) -> str:
            """Search the user's knowledge base using hybrid/MMR retrieval."""
            try:
                results = await _retriever.search(
                    query,
                    limit=limit,
                    category=category or None,
                    search_type="mmr",
                )
                return json.dumps({
                    "results": [
                        {
                            "id": str(r.id),
                            "title": r.title,
                            "content": r.content[:1000],
                            "category": r.category,
                            "score": round(r.score, 3),
                            "source_url": r.source_url,
                        }
                        for r in results
                    ],
                    "total": len(results),
                })
            except Exception as exc:
                return json.dumps({"results": [], "error": str(exc)})

        tool_registry.override_tool_impl("search_knowledge", _search_knowledge_impl)

        return agent

    async def list_available(self) -> list[dict]:
        """Return a summary of all active agents."""
        result = await self._db.execute(
            select(AgentModel).where(AgentModel.is_active == True)
        )
        agents = result.scalars().all()
        return [
            {
                "name": a.name,
                "display_name": a.display_name,
                "description": a.description,
                "model": a.model,
                "available_tools": a.available_tools,
            }
            for a in agents
        ]

    @property
    def llm_provider(self) -> LLMProvider:
        return self._llm

    @property
    def router(self) -> AgentRouter:
        return self._router

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _load_agent(self, name: str) -> AgentModel:
        result = await self._db.execute(
            select(AgentModel).where(
                AgentModel.name == name,
                AgentModel.is_active == True,
            )
        )
        agent = result.scalar_one_or_none()
        if agent is None:
            raise ValueError(f"Agent '{name}' not found or inactive in database")
        return agent

    async def _load_user_config(
        self, agent_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[UserAgentConfig]:
        result = await self._db.execute(
            select(UserAgentConfig).where(
                UserAgentConfig.agent_id == agent_id,
                UserAgentConfig.user_id == user_id,
                UserAgentConfig.is_enabled == True,
            )
        )
        return result.scalar_one_or_none()
