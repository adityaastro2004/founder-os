"""
Founder OS — A2A Agent Router
================================
Agent-to-Agent (A2A) routing and delegation protocol.

Inspired by Google's A2A spec, simplified for backend-native use:

  ┌────────────┐     delegate()     ┌────────────┐
  │  Planner   │ ──────────────────▶│  Research   │
  │  Agent     │◀──────────────────│  Agent      │
  └────────────┘    AgentResult     └────────────┘
        │                                  │
        │         broadcast()              │
        ▼                                  ▼
  ┌──────────────────────────────────────────┐
  │              Event Bus (Redis)            │
  └──────────────────────────────────────────┘

Key concepts:
  - **AgentCard**: describes what an agent can do (capabilities, input types)
  - **AgentMessage**: inter-agent communication envelope
  - **AgentRouter**: routes tasks to the best agent, handles delegation
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from app.agents.event_bus import Event, EventBus

if TYPE_CHECKING:
    from app.agents.base import BaseAgent, AgentResult

logger = logging.getLogger(__name__)


# ============================================================================
# Agent Card (A2A capability declaration)
# ============================================================================

@dataclass
class AgentCard:
    """
    Describes an agent's identity and capabilities.
    Other agents use this to decide who to delegate to.
    """
    name: str
    display_name: str
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    accepted_input_types: list[str] = field(default_factory=lambda: ["text"])
    output_types: list[str] = field(default_factory=lambda: ["text"])
    max_concurrency: int = 5
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "capabilities": self.capabilities,
            "accepted_input_types": self.accepted_input_types,
            "output_types": self.output_types,
            "tags": self.tags,
        }


# ============================================================================
# Agent Message (inter-agent envelope)
# ============================================================================

@dataclass
class AgentMessage:
    """A message sent between agents."""
    from_agent: str
    to_agent: str
    task: str                                    # what the target agent should do
    context: dict[str, Any] = field(default_factory=dict)  # extra data
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    parent_id: str | None = None                 # for threading / tracing
    correlation_id: str = ""                     # trace across delegation chain
    timestamp: float = field(default_factory=time.time)
    priority: int = 5                            # 1 = highest, 10 = lowest

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "task": self.task,
            "context": self.context,
            "message_id": self.message_id,
            "parent_id": self.parent_id,
            "correlation_id": self.correlation_id,
            "priority": self.priority,
        }


# ============================================================================
# Delegation Result
# ============================================================================

@dataclass
class DelegationResult:
    """Wraps the result of an agent-to-agent delegation."""
    from_agent: str
    to_agent: str
    task: str
    success: bool
    content: str = ""
    error: str = ""
    tokens_used: int = 0
    duration_seconds: float = 0.0
    message_id: str = ""
    correlation_id: str = ""


# ============================================================================
# Agent Router
# ============================================================================

class AgentRouter:
    """
    Routes tasks between agents. Maintains a registry of AgentCards
    and provides delegation / routing capabilities.

    The router does NOT own agent instances — it receives a lookup
    function from the registry that can instantiate agents on demand.
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._cards: dict[str, AgentCard] = {}
        self._event_bus = event_bus
        # Agent factory: name → callable that returns an agent instance
        self._agent_factory: dict[str, Any] = {}

    # -- Card management --------------------------------------------------

    def register_card(self, card: AgentCard) -> None:
        """Register an agent's capability card."""
        self._cards[card.name] = card
        logger.info("Registered agent card: %s", card.name)

    def register_factory(self, agent_name: str, factory: Any) -> None:
        """
        Register a factory function that creates an agent instance.
        The factory should be: async (str, UUID, str|None) -> BaseAgent
        """
        self._agent_factory[agent_name] = factory

    def get_card(self, name: str) -> AgentCard | None:
        return self._cards.get(name)

    def list_cards(self) -> list[AgentCard]:
        return list(self._cards.values())

    # -- Routing ----------------------------------------------------------

    def route(
        self,
        task: str,
        from_agent: str = "",
        required_capabilities: list[str] | None = None,
        exclude: list[str] | None = None,
    ) -> str | None:
        """
        Select the best agent for a task based on capabilities.

        Returns the agent name, or None if no suitable agent found.
        Simple capability matching — can be enhanced with LLM routing later.
        """
        exclude_set = set(exclude or [])
        candidates: list[tuple[str, int]] = []

        for name, card in self._cards.items():
            if name in exclude_set:
                continue
            if name == from_agent:
                continue  # don't self-delegate

            if required_capabilities:
                match_count = sum(
                    1 for cap in required_capabilities
                    if cap in card.capabilities
                )
                if match_count > 0:
                    candidates.append((name, match_count))
            else:
                # Score by keyword matching in description + capabilities
                task_lower = task.lower()
                score = 0
                for cap in card.capabilities:
                    if cap.lower() in task_lower:
                        score += 2
                for tag in card.tags:
                    if tag.lower() in task_lower:
                        score += 1
                if any(word in task_lower for word in card.description.lower().split()):
                    score += 1
                if score > 0:
                    candidates.append((name, score))

        if not candidates:
            return None

        # Return the highest-scoring candidate
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    # -- Delegation -------------------------------------------------------

    async def delegate(
        self,
        message: AgentMessage,
        *,
        user_id: Any = None,
        session_id: str | None = None,
    ) -> DelegationResult:
        """
        Delegate a task from one agent to another.
        Creates the target agent via the factory, runs it, and returns the result.
        """
        target_name = message.to_agent
        correlation = message.correlation_id or message.message_id

        # Emit delegation.requested event
        if self._event_bus:
            await self._event_bus.publish(Event(
                type="delegation.requested",
                agent=message.from_agent,
                data={
                    **message.to_dict(),
                    "user_id": str(user_id) if user_id is not None else "",
                },
                correlation_id=correlation,
            ))

        factory = self._agent_factory.get(target_name)
        if factory is None:
            error = f"No factory registered for agent '{target_name}'"
            logger.error(error)
            return DelegationResult(
                from_agent=message.from_agent,
                to_agent=target_name,
                task=message.task,
                success=False,
                error=error,
                message_id=message.message_id,
                correlation_id=correlation,
            )

        try:
            # Build context string from message
            context_parts = [message.task]
            if message.context:
                context_parts.append(
                    f"\n<delegation_context>\n"
                    f"Delegated by: {message.from_agent}\n"
                    + "\n".join(f"{k}: {v}" for k, v in message.context.items())
                    + "\n</delegation_context>"
                )
            full_input = "\n".join(context_parts)

            # Get agent from factory
            agent = await factory(target_name, user_id, session_id)

            # Run the agent
            start = time.time()
            result = await agent.run(full_input)
            duration = time.time() - start

            delegation_result = DelegationResult(
                from_agent=message.from_agent,
                to_agent=target_name,
                task=message.task,
                success=True,
                content=result.content,
                tokens_used=result.tokens_used,
                duration_seconds=duration,
                message_id=message.message_id,
                correlation_id=correlation,
            )

            # Emit delegation.completed event
            if self._event_bus:
                await self._event_bus.publish(Event(
                    type="delegation.completed",
                    agent=target_name,
                    data={
                        "from_agent": message.from_agent,
                        "task": message.task,
                        "success": True,
                        "tokens_used": result.tokens_used,
                        "user_id": str(user_id) if user_id is not None else "",
                    },
                    correlation_id=correlation,
                ))

            return delegation_result

        except Exception as exc:
            logger.exception("Delegation to '%s' failed", target_name)

            if self._event_bus:
                await self._event_bus.publish(Event(
                    type="delegation.failed",
                    agent=target_name,
                    data={
                        "from_agent": message.from_agent,
                        "task": message.task,
                        "error": str(exc),
                        "user_id": str(user_id) if user_id is not None else "",
                    },
                    correlation_id=correlation,
                ))

            return DelegationResult(
                from_agent=message.from_agent,
                to_agent=target_name,
                task=message.task,
                success=False,
                error=str(exc),
                message_id=message.message_id,
                correlation_id=correlation,
            )

    # -- Broadcast --------------------------------------------------------

    async def broadcast(
        self,
        event_type: str,
        data: dict[str, Any],
        source_agent: str = "",
    ) -> None:
        """Broadcast an event to all agents via the event bus."""
        if self._event_bus:
            await self._event_bus.publish(Event(
                type=event_type,
                agent=source_agent,
                data=data,
            ))

    # -- Introspection ----------------------------------------------------

    @property
    def registered_agents(self) -> list[str]:
        return list(self._cards.keys())

    def get_capabilities_summary(self) -> str:
        """
        Return a text summary of all agents and their capabilities,
        suitable for injection into an LLM system prompt.
        """
        if not self._cards:
            return ""

        parts = ["<available_agents>"]
        for card in self._cards.values():
            caps = ", ".join(card.capabilities) if card.capabilities else "general"
            parts.append(
                f"- **{card.display_name}** (`{card.name}`): {card.description}\n"
                f"  Capabilities: {caps}"
            )
        parts.append("</available_agents>")
        return "\n".join(parts)
