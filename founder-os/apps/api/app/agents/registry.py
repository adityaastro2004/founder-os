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
import uuid
from typing import Any, Optional

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agents import AGENT_CLASSES
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
from app.agents.router import AgentCard, AgentRouter
from app.agents.tool_protocol import LocalToolProvider, ToolRegistry
from app.models import Agent as AgentModel, UserAgentConfig


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
        )

        # Event bus (shared across agents)
        self._event_bus = EventBus(redis)

        # A2A router (shared across agents)
        self._router = AgentRouter(event_bus=self._event_bus)

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
            ) -> BaseAgent:
                return await _self.get(agent_name, user_id, session_id=session_id)

            self._router.register_factory(name, _factory)

    # -- Provider config helpers -----------------------------------------

    @staticmethod
    def _get_api_key(settings: Any) -> str:
        if settings.LLM_PROVIDER == "anthropic":
            return settings.ANTHROPIC_API_KEY
        elif settings.LLM_PROVIDER == "openai_compatible":
            return settings.OPENAI_API_KEY
        return ""  # Ollama doesn't need a key

    @staticmethod
    def _get_base_url(settings: Any) -> str:
        if settings.LLM_PROVIDER == "ollama":
            return settings.OLLAMA_BASE_URL
        elif settings.LLM_PROVIDER == "openai_compatible":
            return settings.OPENAI_BASE_URL
        return ""

    @staticmethod
    def _get_model(settings: Any) -> str:
        if settings.LLM_PROVIDER == "ollama":
            return settings.OLLAMA_MODEL
        elif settings.LLM_PROVIDER == "anthropic":
            return settings.ANTHROPIC_MODEL
        elif settings.LLM_PROVIDER == "openai_compatible":
            return settings.OPENAI_MODEL
        return ""

    # -- Public API -------------------------------------------------------

    async def get(
        self,
        agent_name: str,
        user_id: uuid.UUID,
        *,
        session_id: str | None = None,
    ) -> BaseAgent:
        """
        Build and return a fully-initialised agent.

        Args:
            agent_name: Agent slug (e.g. "planner", "content").
            user_id:    The authenticated user's UUID.
            session_id: Optional session identifier for memory scoping.
        """
        # 1. Resolve the Python class
        agent_cls = AGENT_CLASSES.get(agent_name)
        if agent_cls is None:
            raise ValueError(
                f"Unknown agent '{agent_name}'. "
                f"Available: {list(AGENT_CLASSES.keys())}"
            )

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

        # 5. Build tool registry with local tools
        tool_registry = ToolRegistry()
        tool_registry.add_provider(
            LocalToolProvider(allowed_tools=config.tool_names)
        )
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
        memory = AgentMemory(
            conversation=conversation,
            working=working,
            long_term=long_term,
            shared=shared,
        )

        # 7. Instantiate with all components
        agent = agent_cls(
            config=config,
            memory=memory,
            llm=self._llm,
            tools=tool_registry,
            router=self._router,
            event_bus=self._event_bus,
        )

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
