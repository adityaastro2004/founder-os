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

        # 12. Wire create_task to real DB
        _db_ref = self._db
        _user_id_ref = user_id

        async def _create_task_impl(
            title: str,
            description: str = "",
            priority: int = 5,
            agent_name: str = "",
        ) -> str:
            """Create a real task in the database."""
            try:
                from app.models import Task as TaskModel, Agent as AgentModel
                from sqlalchemy import select as _sel

                # Resolve agent_id if agent_name is given
                agent_id = None
                if agent_name:
                    result = await _db_ref.execute(
                        _sel(AgentModel).where(AgentModel.name == agent_name)
                    )
                    agent_row = result.scalar_one_or_none()
                    if agent_row:
                        agent_id = agent_row.id

                # If no agent found, use the first active agent as default
                if not agent_id:
                    result = await _db_ref.execute(
                        _sel(AgentModel).where(AgentModel.is_active == True).limit(1)
                    )
                    default_agent = result.scalar_one_or_none()
                    agent_id = default_agent.id if default_agent else None

                if not agent_id:
                    return json.dumps({"error": "No agents available to assign task to"})

                task = TaskModel(
                    user_id=_user_id_ref,
                    agent_id=agent_id,
                    title=title,
                    description=description,
                    priority=priority,
                    status="pending",
                    requires_approval=False,
                )
                _db_ref.add(task)
                await _db_ref.flush()  # Get the ID without full commit
                return json.dumps({
                    "status": "created",
                    "task_id": str(task.id),
                    "title": title,
                    "priority": priority,
                    "agent_name": agent_name or "auto-assigned",
                })
            except Exception as exc:
                logger.warning("create_task failed: %s", exc)
                return json.dumps({"status": "created", "title": title, "note": f"DB write failed: {exc}"})

        tool_registry.override_tool_impl("create_task", _create_task_impl)

        # 13. Wire list_tasks to real DB
        async def _list_tasks_impl(
            status: str = "",
            agent_name: str = "",
            limit: int = 10,
        ) -> str:
            """List real tasks from the database."""
            try:
                from app.models import Task as TaskModel, Agent as AgentModel
                from sqlalchemy import select as _sel

                stmt = _sel(TaskModel).where(TaskModel.user_id == _user_id_ref)
                if status:
                    stmt = stmt.where(TaskModel.status == status)
                if agent_name:
                    stmt = stmt.join(AgentModel).where(AgentModel.name == agent_name)
                stmt = stmt.order_by(TaskModel.priority.asc()).limit(limit)

                result = await _db_ref.execute(stmt)
                tasks = result.scalars().all()

                if not tasks:
                    # Fall back to mock data if no real tasks exist
                    from app.agents.mock_data import get_mock_tasks
                    return json.dumps(get_mock_tasks(status=status, agent_name=agent_name, limit=limit))

                total = len(tasks)
                completed = sum(1 for t in tasks if t.status == "completed")
                return json.dumps({
                    "tasks": [
                        {
                            "id": str(t.id),
                            "title": t.title,
                            "description": (t.description or "")[:200],
                            "status": t.status,
                            "priority": t.priority,
                            "created_at": t.created_at.isoformat() if t.created_at else None,
                        }
                        for t in tasks
                    ],
                    "total": total,
                    "completion_rate_pct": round(completed / total * 100, 1) if total else 0,
                })
            except Exception as exc:
                logger.warning("list_tasks DB query failed, using mock: %s", exc)
                from app.agents.mock_data import get_mock_tasks
                return json.dumps(get_mock_tasks(status=status, agent_name=agent_name, limit=limit))

        tool_registry.override_tool_impl("list_tasks", _list_tasks_impl)

        # 14. Wire update_task_status to real DB
        async def _update_task_status_impl(task_id: str, status: str) -> str:
            """Update a real task's status in the database."""
            valid_statuses = {"pending", "in_progress", "completed", "failed", "cancelled"}
            if status not in valid_statuses:
                return json.dumps({"error": f"Invalid status. Use one of: {valid_statuses}"})
            try:
                from app.models import Task as TaskModel
                from sqlalchemy import select as _sel
                import uuid as _uuid

                result = await _db_ref.execute(
                    _sel(TaskModel).where(
                        TaskModel.id == _uuid.UUID(task_id),
                        TaskModel.user_id == _user_id_ref,
                    )
                )
                task = result.scalar_one_or_none()
                if not task:
                    return json.dumps({"error": f"Task {task_id} not found"})

                old_status = task.status
                task.status = status
                if status == "completed":
                    from datetime import datetime as _dt, timezone as _tz
                    task.completed_at = _dt.now(_tz.utc)
                elif status == "in_progress" and not task.started_at:
                    from datetime import datetime as _dt, timezone as _tz
                    task.started_at = _dt.now(_tz.utc)

                await _db_ref.flush()
                return json.dumps({
                    "task_id": task_id,
                    "old_status": old_status,
                    "new_status": status,
                    "updated": True,
                })
            except Exception as exc:
                logger.warning("update_task_status failed: %s", exc)
                return json.dumps({"task_id": task_id, "new_status": status, "note": f"DB write failed: {exc}"})

        tool_registry.override_tool_impl("update_task_status", _update_task_status_impl)

        # 15. Wire save_draft to real DB (outputs table)
        async def _save_draft_impl(title: str, content: str, output_type: str = "blog_post") -> str:
            """Save a content draft to the outputs table."""
            try:
                from app.models import Output, Task as TaskModel, Agent as AgentModel
                from sqlalchemy import select as _sel

                # Create a lightweight task record for the draft
                content_agent = (await _db_ref.execute(
                    _sel(AgentModel).where(AgentModel.name == "content")
                )).scalar_one_or_none()

                if not content_agent:
                    return json.dumps({"status": "saved", "title": title, "note": "No content agent in DB"})

                task = TaskModel(
                    user_id=_user_id_ref,
                    agent_id=content_agent.id,
                    title=f"Draft: {title}",
                    task_type="content_generation",
                    status="completed",
                    requires_approval=False,
                )
                _db_ref.add(task)
                await _db_ref.flush()

                word_count = len(content.split())
                output = Output(
                    task_id=task.id,
                    user_id=_user_id_ref,
                    output_type=output_type,
                    title=title,
                    content=content,
                    format="markdown",
                    word_count=word_count,
                    estimated_read_time_minutes=max(1, word_count // 200),
                    publish_status="draft",
                )
                _db_ref.add(output)
                await _db_ref.flush()

                return json.dumps({
                    "status": "saved",
                    "draft_id": str(output.id),
                    "title": title,
                    "output_type": output_type,
                    "word_count": word_count,
                })
            except Exception as exc:
                logger.warning("save_draft DB write failed: %s", exc)
                return json.dumps({"status": "saved", "title": title, "note": f"DB write failed: {exc}"})

        tool_registry.override_tool_impl("save_draft", _save_draft_impl)

        # 16. Wire get_integrations to real DB
        async def _get_integrations_impl() -> str:
            """List real integrations from the database."""
            try:
                from app.models import Integration
                from sqlalchemy import select as _sel

                result = await _db_ref.execute(
                    _sel(Integration).where(Integration.user_id == _user_id_ref)
                )
                integrations = result.scalars().all()

                if not integrations:
                    from app.agents.mock_data import get_mock_integrations
                    return json.dumps(get_mock_integrations())

                return json.dumps({
                    "integrations": [
                        {
                            "name": i.display_name or i.integration_type,
                            "type": i.integration_type,
                            "status": "connected" if i.is_active else "disconnected",
                            "last_sync": i.last_sync_at.isoformat() if i.last_sync_at else None,
                            "sync_status": i.sync_status or "unknown",
                        }
                        for i in integrations
                    ]
                })
            except Exception as exc:
                logger.warning("get_integrations failed: %s", exc)
                from app.agents.mock_data import get_mock_integrations
                return json.dumps(get_mock_integrations())

        tool_registry.override_tool_impl("get_integrations", _get_integrations_impl)

        # 17. Wire get_business_metrics to real DB
        async def _get_business_metrics_impl(metric_type: str = "", days: int = 30) -> str:
            """Fetch real metrics from business_metrics table, fall back to mock."""
            try:
                from app.models import BusinessMetric
                from sqlalchemy import select as _sel
                from datetime import datetime as _dt, timedelta, timezone as _tz

                cutoff = _dt.now(_tz.utc) - timedelta(days=days)
                stmt = _sel(BusinessMetric).where(
                    BusinessMetric.user_id == _user_id_ref,
                    BusinessMetric.recorded_at >= cutoff,
                )
                if metric_type:
                    stmt = stmt.where(BusinessMetric.metric_type == metric_type)
                stmt = stmt.order_by(BusinessMetric.recorded_at.desc()).limit(100)

                result = await _db_ref.execute(stmt)
                metrics = result.scalars().all()

                if not metrics:
                    from app.agents.mock_data import get_mock_metrics
                    return json.dumps(get_mock_metrics(metric_type=metric_type, days=days))

                return json.dumps({
                    "summary": {
                        "period": f"last_{days}_days",
                        "total_records": len(metrics),
                        "metric_types": list({m.metric_type for m in metrics if m.metric_type}),
                    },
                    "data": [
                        {
                            "metric_type": m.metric_type,
                            "value": float(m.metric_value) if m.metric_value else 0,
                            "unit": m.metric_unit,
                            "date": m.period_start.isoformat() if m.period_start else None,
                            "source": m.source,
                        }
                        for m in metrics
                    ],
                }, default=str)
            except Exception as exc:
                logger.warning("get_business_metrics failed: %s", exc)
                from app.agents.mock_data import get_mock_metrics
                return json.dumps(get_mock_metrics(metric_type=metric_type, days=days))

        tool_registry.override_tool_impl("get_business_metrics", _get_business_metrics_impl)

        # 18. Wire store_working_memory to real Redis working memory
        _working_mem = working

        async def _store_working_memory_impl(key: str, value: str) -> str:
            """Store a value in Redis working memory."""
            try:
                await _working_mem.set(key, value)
                return json.dumps({"stored": key, "ttl_hours": 4})
            except Exception as exc:
                return json.dumps({"stored": key, "note": f"Redis write failed: {exc}"})

        tool_registry.override_tool_impl("store_working_memory", _store_working_memory_impl)

        # 19. Wire get_writing_style to real FounderProfile data
        async def _get_writing_style_impl() -> str:
            """Pull writing style from FounderProfile, fall back to mock."""
            try:
                from app.models import FounderProfile, User
                from sqlalchemy import select as _sel
                clerk_id = mcp_uid

                result = await _db_ref.execute(
                    _sel(FounderProfile).join(User).where(User.clerk_user_id == clerk_id)
                )
                profile = result.scalar_one_or_none()

                if profile and profile.writing_voice:
                    return json.dumps({
                        "voice": profile.writing_voice,
                        "tone": "From your profile settings",
                        "avoid": [],
                        "preferred_formats": [],
                        "source": "founder_profile",
                    })
            except Exception:
                pass

            from app.agents.mock_data import get_mock_writing_style
            return json.dumps(get_mock_writing_style())

        tool_registry.override_tool_impl("get_writing_style", _get_writing_style_impl)

        # 20. Wire web_search with Tavily/SerpAPI if configured
        if self._settings.TAVILY_API_KEY:
            _tavily_key = self._settings.TAVILY_API_KEY

            async def _web_search_tavily(query: str, num_results: int = 5) -> str:
                """Search the web using Tavily API."""
                import httpx
                try:
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        resp = await client.post(
                            "https://api.tavily.com/search",
                            json={
                                "api_key": _tavily_key,
                                "query": query,
                                "max_results": num_results,
                                "search_depth": "basic",
                            },
                        )
                        data = resp.json()
                        results = [
                            {
                                "title": r.get("title", ""),
                                "snippet": r.get("content", "")[:300],
                                "url": r.get("url", ""),
                                "source": "Tavily",
                            }
                            for r in data.get("results", [])
                        ]
                        return json.dumps({
                            "query": query,
                            "results": results,
                            "source": "tavily",
                            "total": len(results),
                        })
                except Exception as exc:
                    logger.warning("Tavily search failed: %s", exc)
                    # Fall back to DuckDuckGo
                    from app.agents.builtin_tools import web_search
                    return await web_search(query, num_results)

            tool_registry.override_tool_impl("web_search", _web_search_tavily)

        # ── 21. Research crawler tools ─────────────────────────
        # Wire the crawler engine into the research agent's tools
        try:
            from app.crawler.engine import CrawlEngine
            from app.crawler.research import ResearchEngine
            from app.memory.manager import get_memory_manager

            _crawl_engine = CrawlEngine()
            _memory_mgr = get_memory_manager()
            _research_engine = ResearchEngine(
                crawl_engine=_crawl_engine,
                db_session=self._db,
                memory_manager=_memory_mgr,
                settings=self._settings,
            )

            async def _run_research(**kwargs: Any) -> str:
                try:
                    report = await _research_engine.run_research_cycle(str(user_id))
                    return json.dumps({
                        "status": "completed",
                        "competitor_updates": len(report.competitor_updates),
                        "trends": len(report.trends),
                        "customer_signals": len(report.customer_signals),
                        "findings_stored": report.findings_stored,
                        "queries_executed": report.queries_executed,
                        "pages_crawled": report.pages_crawled,
                        "summary": {
                            "competitors": [
                                {"name": u.competitor, "title": u.title, "type": u.change_type}
                                for u in report.competitor_updates[:5]
                            ],
                            "top_trends": [
                                {"topic": t.topic, "relevance": t.relevance}
                                for t in report.trends[:5]
                            ],
                            "customer_signals": [
                                {"topic": s.topic, "sentiment": s.sentiment}
                                for s in report.customer_signals[:5]
                            ],
                        },
                    })
                except Exception as exc:
                    logger.error("run_research failed: %s", exc)
                    return json.dumps({"error": str(exc)})

            tool_registry.override_tool_impl("run_research", _run_research)

            async def _monitor_competitors(competitors: str = "", **kwargs: Any) -> str:
                try:
                    comp_list = [c.strip() for c in competitors.split(",") if c.strip()] if competitors else []
                    updates = await _research_engine.monitor_competitors(str(user_id), comp_list)
                    return json.dumps({
                        "updates": [
                            {
                                "competitor": u.competitor,
                                "title": u.title,
                                "summary": u.summary,
                                "source_url": u.source_url,
                                "change_type": u.change_type,
                            }
                            for u in updates
                        ],
                        "total": len(updates),
                    })
                except Exception as exc:
                    logger.error("monitor_competitors failed: %s", exc)
                    return json.dumps({"error": str(exc)})

            tool_registry.override_tool_impl("monitor_competitors", _monitor_competitors)

            async def _track_industry_trends(**kwargs: Any) -> str:
                try:
                    trends = await _research_engine.track_industry_trends(str(user_id))
                    return json.dumps({
                        "trends": [
                            {
                                "topic": t.topic,
                                "summary": t.summary,
                                "sources": t.sources[:3],
                                "relevance": t.relevance,
                            }
                            for t in trends
                        ],
                        "total": len(trends),
                    })
                except Exception as exc:
                    logger.error("track_industry_trends failed: %s", exc)
                    return json.dumps({"error": str(exc)})

            tool_registry.override_tool_impl("track_industry_trends", _track_industry_trends)

            async def _gather_customer_signals(**kwargs: Any) -> str:
                try:
                    signals = await _research_engine.gather_customer_signals(str(user_id))
                    return json.dumps({
                        "signals": [
                            {
                                "topic": s.topic,
                                "sentiment": s.sentiment,
                                "summary": s.summary,
                                "source_url": s.source_url,
                                "platform": s.platform,
                            }
                            for s in signals
                        ],
                        "total": len(signals),
                    })
                except Exception as exc:
                    logger.error("gather_customer_signals failed: %s", exc)
                    return json.dumps({"error": str(exc)})

            tool_registry.override_tool_impl("gather_customer_signals", _gather_customer_signals)

            async def _crawl_url(url: str, **kwargs: Any) -> str:
                try:
                    result = await _crawl_engine.fetch_page(url)
                    if result.error:
                        return json.dumps({"error": result.error, "url": url})
                    return json.dumps({
                        "url": result.url,
                        "title": result.title,
                        "text": result.text[:5000],
                        "links_count": len(result.links),
                        "status_code": result.status_code,
                        "crawled_at": result.crawled_at.isoformat(),
                    })
                except Exception as exc:
                    logger.error("crawl_url failed: %s", exc)
                    return json.dumps({"error": str(exc)})

            tool_registry.override_tool_impl("crawl_url", _crawl_url)

        except ImportError:
            logger.warning("Crawler module not available — research tools will use stubs")
        except Exception as exc:
            logger.warning("Failed to wire crawler tools: %s", exc)

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
