"""
Founder OS — BaseAgent (v2)
============================
Enhanced base class with deep architecture support:

  ┌──────────────────────────────────────────────────────┐
  │                      BaseAgent                        │
  │  ┌──────────┐ ┌────────────┐ ┌───────────────────┐  │
  │  │  Memory   │ │ ToolRegistry│ │  LLM Interface    │  │
  │  │ 3-layer  │ │ (MCP-compat)│ │ Ollama/Anthropic  │  │
  │  └──────────┘ └────────────┘ └───────────────────┘  │
  │  ┌──────────┐ ┌────────────────────────────────┐    │
  │  │  Router  │ │     Execution Engine             │    │
  │  │  (A2A)   │ │  LLM → Tools → Delegation loop  │    │
  │  └──────────┘ └────────────────────────────────┘    │
  │  ┌──────────────────────────────────────────────┐   │
  │  │               Event Bus (Redis)               │   │
  │  └──────────────────────────────────────────────┘   │
  └──────────────────────────────────────────────────────┘

Subclasses declare their identity, tools, and system prompt.
The engine handles the rest.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.agents.event_bus import Event, EventBus
from app.agents.execution import ExecutionEngine, ExecutionResult
from app.agents.llm import LLMMessage, LLMProvider, Role, ToolSchema
from app.agents.memory import AgentMemory
from app.agents.router import AgentCard, AgentMessage, AgentRouter, DelegationResult
from app.agents.tool_protocol import ToolRegistry

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.agents.approval import ApprovalGate
    from app.retrieval.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)


# ============================================================================
# Data types
# ============================================================================

@dataclass
class AgentConfig:
    """Runtime configuration for an agent, loaded from DB + user overrides."""

    name: str
    display_name: str
    model: str = "claude-sonnet-4-20250514"
    temperature: float = 0.7
    max_tokens: int = 4096
    max_tool_rounds: int = 15
    system_prompt: str = ""
    tool_names: list[str] = field(default_factory=list)
    custom_instructions: str | None = None  # per-user overlay


@dataclass
class AgentResult:
    """The output of a single agent run."""

    content: str
    tool_calls_made: list[dict[str, Any]] = field(default_factory=list)
    tokens_used: int = 0
    cost_usd: float = 0.0
    duration_seconds: float = 0.0
    stop_reason: str = ""
    model: str = ""
    steps: list[Any] = field(default_factory=list)  # ExecutionStep trace
    delegations: list[DelegationResult] = field(default_factory=list)
    pending_approvals: list[dict[str, Any]] = field(default_factory=list)


# ============================================================================
# BaseAgent
# ============================================================================

class BaseAgent:
    """
    Enhanced base for every Founder OS agent.

    Composes:
      - LLMProvider (Ollama / Anthropic / OpenAI-compat)
      - ToolRegistry (local tools + MCP servers)
      - AgentMemory (conversation + Redis working + pgvector RAG)
      - AgentRouter (A2A delegation)
      - EventBus (Redis pub/sub)
      - ExecutionEngine (agentic loop with retries + cost tracking)

    Subclasses MUST set:
        ``name``                — unique agent slug
        ``default_system_prompt`` — personality / instructions

    Subclasses MAY set:
        ``default_tools``       — list of tool names
        ``capabilities``        — what this agent can do (for A2A routing)
        ``tags``                — keywords for routing
    """

    # -- Override in subclasses ------------------------------------------
    name: str = ""
    default_system_prompt: str = ""
    default_tools: list[str] = []
    capabilities: list[str] = []
    tags: list[str] = []

    def __init__(
        self,
        config: AgentConfig,
        memory: AgentMemory,
        llm: LLMProvider,
        tools: ToolRegistry,
        router: AgentRouter | None = None,
        event_bus: EventBus | None = None,
        approval_gate: "ApprovalGate | None" = None,
        user_id: str = "",
        embedder: "EmbeddingProvider | None" = None,
    ) -> None:
        self.config = config
        self.memory = memory
        self.llm = llm
        self.tools = tools
        self.router = router
        self.event_bus = event_bus
        self.approval_gate = approval_gate
        self.user_id = user_id
        self.clerk_user_id: str = ""  # Set by registry; canonical ID for profile intelligence
        self._embedder = embedder

        # Build execution engine
        self._engine = ExecutionEngine(
            llm=llm,
            tools=tools,
            max_rounds=config.max_tool_rounds,
            parallel_tool_calls=True,
            approval_gate=approval_gate,
            user_id=user_id,
            event_bus=event_bus,
        )

    # -- A2A Card --------------------------------------------------------

    def get_card(self) -> AgentCard:
        """Return this agent's capability card for A2A routing."""
        return AgentCard(
            name=self.name,
            display_name=self.config.display_name,
            description=self.config.system_prompt[:200] if self.config.system_prompt else "",
            capabilities=self.capabilities or [],
            tags=self.tags or [],
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        user_input: str,
        *,
        query_embedding: list[float] | None = None,
        extra_context: str | None = None,
    ) -> AgentResult:
        """
        Execute the full agentic loop via the ExecutionEngine.
        """
        # 1. Emit agent.started event
        if self.event_bus:
            await self.event_bus.publish(Event(
                type="agent.started",
                agent=self.name,
                data={"input_preview": user_input[:200]},
            ))

        # 1b. Auto-embed the user query for RAG (if embedder is available)
        if query_embedding is None and self._embedder is not None:
            try:
                query_embedding = await self._embedder.embed(user_input)
            except Exception as exc:
                logger.warning("Auto-embedding failed, skipping RAG: %s", exc)

        # 2. Build system prompt with memory + router context
        system_prompt = await self._build_system_prompt(
            query=user_input,
            query_embedding=query_embedding,
            extra_context=extra_context,
        )

        # 3. Build messages list
        self.memory.conversation.add_user(user_input)
        messages = self._build_llm_messages()

        # 4. Pre-run hook
        await self.before_run(user_input)

        # 5. Run execution engine
        exec_result: ExecutionResult = await self._engine.run(
            messages,
            system=system_prompt,
            model=self.config.model,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            agent_name=self.name,
        )

        # 6. Store assistant response in conversation memory
        if exec_result.content:
            self.memory.conversation.add_assistant(exec_result.content)

        # 7. Build result
        result = AgentResult(
            content=exec_result.content,
            tool_calls_made=exec_result.tool_calls_log,
            tokens_used=exec_result.total_tokens,
            cost_usd=exec_result.cost_usd,
            duration_seconds=exec_result.duration_seconds,
            stop_reason=exec_result.stop_reason,
            model=exec_result.model,
            steps=exec_result.steps,
            pending_approvals=exec_result.pending_approvals,
        )

        # 8. Post-run hook
        await self.after_run(user_input, result)

        # 9. Emit agent.completed event
        if self.event_bus:
            await self.event_bus.publish(Event(
                type="agent.completed",
                agent=self.name,
                data={
                    "tokens_used": result.tokens_used,
                    "tool_calls": len(result.tool_calls_made),
                    "cost_usd": result.cost_usd,
                    "duration": result.duration_seconds,
                },
            ))

        return result

    # ------------------------------------------------------------------
    # Delegation (A2A)
    # ------------------------------------------------------------------

    async def delegate_to(
        self,
        target_agent: str,
        task: str,
        context: dict[str, Any] | None = None,
        *,
        user_id: Any = None,
        session_id: str | None = None,
    ) -> DelegationResult:
        """
        Delegate a task to another agent via the A2A router.

        Usage in tool implementations or subclass logic:
            result = await self.delegate_to("research", "Find competitors for X")
        """
        if not self.router:
            return DelegationResult(
                from_agent=self.name,
                to_agent=target_agent,
                task=task,
                success=False,
                error="No router configured — cannot delegate",
            )

        message = AgentMessage(
            from_agent=self.name,
            to_agent=target_agent,
            task=task,
            context=context or {},
        )

        return await self.router.delegate(
            message,
            user_id=user_id,
            session_id=session_id,
        )

    async def auto_delegate(
        self,
        task: str,
        *,
        required_capabilities: list[str] | None = None,
        user_id: Any = None,
        session_id: str | None = None,
    ) -> DelegationResult | None:
        """
        Automatically route a task to the best agent.
        Returns None if no suitable agent found.
        """
        if not self.router:
            return None

        target = self.router.route(
            task,
            from_agent=self.name,
            required_capabilities=required_capabilities,
        )
        if not target:
            return None

        return await self.delegate_to(
            target, task,
            user_id=user_id,
            session_id=session_id,
        )

    # ------------------------------------------------------------------
    # Hooks — override in subclasses
    # ------------------------------------------------------------------

    async def before_run(self, user_input: str) -> None:
        """Called before the agentic loop starts."""
        pass

    async def after_run(self, user_input: str, result: AgentResult) -> None:
        """Called after the loop completes."""
        pass

    # ------------------------------------------------------------------
    # System prompt assembly
    # ------------------------------------------------------------------

    async def _build_system_prompt(
        self,
        query: str | None = None,
        query_embedding: list[float] | None = None,
        extra_context: str | None = None,
    ) -> str:
        """Compose system prompt from base + memory + router + user overrides + user profile."""
        from datetime import datetime, timezone as tz
        parts: list[str] = []

        # Base system prompt
        parts.append(self.config.system_prompt or self.default_system_prompt)

        # Current date/time — always injected so agents know "today"
        now = datetime.now(tz.utc)
        parts.append(
            f"\n<current_datetime>\n"
            f"Current date: {now.strftime('%A, %B %d, %Y')}\n"
            f"Current time: {now.strftime('%H:%M %Z')}\n"
            f"ISO: {now.isoformat()}\n"
            f"</current_datetime>"
        )

        # Per-user custom instructions
        if self.config.custom_instructions:
            parts.append(
                f"\n<user_custom_instructions>\n"
                f"{self.config.custom_instructions}\n"
                f"</user_custom_instructions>"
            )

        # Founder profile — business context, primary goal, industry
        founder_ctx = await self._load_founder_profile_context()
        if founder_ctx:
            parts.append(f"\n{founder_ctx}")

        # User profile intelligence — personalises tone, avoids dislikes, etc.
        profile_ctx = await self._load_user_profile_context()
        if profile_ctx:
            parts.append(f"\n{profile_ctx}")

        # A2A: inject available agents for delegation awareness
        if self.router:
            agents_summary = self.router.get_capabilities_summary()
            if agents_summary:
                parts.append(
                    f"\n<delegation_instructions>\n"
                    f"You can delegate sub-tasks to other specialised agents. "
                    f"When a task falls outside your expertise, mention which "
                    f"agent should handle it.\n"
                    f"{agents_summary}\n"
                    f"</delegation_instructions>"
                )

        # Memory context (working memory + RAG)
        mem_ctx = await self.memory.build_context(
            query=query,
            query_embedding=query_embedding,
        )
        if mem_ctx:
            parts.append(f"\n{mem_ctx}")

        # Extra context (caller-supplied)
        if extra_context:
            parts.append(f"\n<additional_context>\n{extra_context}\n</additional_context>")

        return "\n\n".join(parts)

    async def _load_user_profile_context(self) -> str:
        """Load the user's intelligence profile and format it for the system prompt."""
        # Use clerk_user_id (Clerk ID) which matches how insights are stored,
        # falling back to user_id (UUID) if clerk_user_id wasn't set.
        profile_user_id = self.clerk_user_id or self.user_id
        if not profile_user_id:
            return ""
        try:
            from app.agents.profile_intelligence import ProfileIntelligence
            from app.database import async_session

            async with async_session() as db:
                # Lightweight helper — only reads, no LLM call
                pi = ProfileIntelligence(db, llm_generate=None)  # type: ignore[arg-type]
                return await pi.get_profile_context(profile_user_id)
        except Exception as exc:
            logger.debug("Could not load user profile context: %s", exc)
            return ""

    async def _load_founder_profile_context(self) -> str:
        """Load the founder's business profile and format for the system prompt.
        
        This gives the LLM the core business context: what the company does,
        its primary goal, industry, stage, and team — so every agent
        understands the business it's serving.
        """
        clerk_id = self.clerk_user_id or self.user_id
        if not clerk_id:
            return ""
        try:
            from sqlalchemy import select
            from app.database import async_session
            from app.models import FounderProfile, User

            async with async_session() as db:
                result = await db.execute(
                    select(FounderProfile).join(User).where(
                        User.clerk_user_id == clerk_id
                    )
                )
                profile = result.scalar_one_or_none()
                if not profile:
                    return ""

                parts = ["<founder_business_context>"]
                if profile.business_name:
                    parts.append(f"Company: {profile.business_name}")
                if profile.business_type:
                    parts.append(f"Type: {profile.business_type}")
                if profile.industry:
                    parts.append(f"Industry: {profile.industry}")
                if profile.business_stage:
                    parts.append(f"Stage: {profile.business_stage}")
                if profile.target_audience:
                    parts.append(f"Target audience: {profile.target_audience}")
                if profile.primary_goal:
                    goal_label = profile.primary_goal.replace("_", " ").title()
                    parts.append(f"\nPRIMARY GOAL: {goal_label}")
                if profile.primary_goal_description:
                    parts.append(
                        f"Goal details: {profile.primary_goal_description}\n"
                        f"Everything you do should align with and support this goal."
                    )
                if profile.team_size:
                    parts.append(f"Team size: {profile.team_size}")
                if profile.team_roles:
                    parts.append(f"Team roles: {', '.join(profile.team_roles)}")
                parts.append("</founder_business_context>")
                return "\n".join(parts)
        except Exception as exc:
            logger.debug("Could not load founder profile context: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # Message formatting (provider-agnostic)
    # ------------------------------------------------------------------

    def _build_llm_messages(self) -> list[LLMMessage]:
        """Convert conversation memory to provider-agnostic LLMMessages."""
        msgs: list[LLMMessage] = []
        for m in self.memory.conversation.messages:
            if m.role == "user":
                msgs.append(LLMMessage(role=Role.USER, content=m.content))
            elif m.role == "assistant":
                msgs.append(LLMMessage(role=Role.ASSISTANT, content=m.content))
            elif m.role == "tool":
                msgs.append(LLMMessage(
                    role=Role.TOOL_RESULT,
                    content=m.content,
                    tool_call_id=m.tool_use_id or "",
                ))
        return msgs

    def __repr__(self) -> str:
        tools_count = len(self.config.tool_names) if self.config.tool_names else 0
        return (
            f"<{self.__class__.__name__} name={self.name} "
            f"llm={self.llm.provider_name} tools={tools_count}>"
        )
