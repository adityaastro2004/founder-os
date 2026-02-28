"""
Founder OS — Orchestrator Agent
==================================
Inspired by Stripe's Minions architecture.

The orchestrator sits at the top of the agent hierarchy. It is the
**single entry point** for all user requests. Instead of the user
picking which specialist agent to talk to, the orchestrator:

  1. **Analyses** the user's request
  2. **Plans** which specialist agents (minions) to invoke
  3. **Delegates** subtasks via tool calls (agents-as-tools pattern)
  4. **Synthesises** all results into one coherent response

Design (Stripe Minions-inspired):

  ┌─────────────────────────────────────────────────────────┐
  │                     User Message                         │
  └────────────────────────┬────────────────────────────────┘
                           ▼
  ┌─────────────────────────────────────────────────────────┐
  │                   ORCHESTRATOR                           │
  │                                                         │
  │  1. Understand intent                                   │
  │  2. Decide: handle directly OR delegate                 │
  │  3. Call specialist agents via delegate_task() tool     │
  │  4. Collect results (parallel when independent)         │
  │  5. Synthesise final response                           │
  └───────┬──────────┬──────────┬──────────┬───────────────┘
          ▼          ▼          ▼          ▼
      ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
      │Planner │ │Content │ │Research│ │  Ops   │  ...
      │ Agent  │ │ Agent  │ │ Agent  │ │ Agent  │
      └────────┘ └────────┘ └────────┘ └────────┘

Key principles:
  - Agents-as-tools: each specialist is exposed to the LLM as a callable tool
  - The orchestrator's LLM decides the routing — no hardcoded if/else
  - Subtasks can run in parallel (the execution engine handles this)
  - Full trace: every delegation step is logged and visible
  - Graceful fallback: for simple questions, the orchestrator answers directly
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from app.agents.base import BaseAgent, AgentConfig, AgentResult
from app.agents.event_bus import Event, EventBus
from app.agents.execution import ExecutionEngine, ExecutionResult
from app.agents.llm import LLMMessage, LLMProvider, Role, ToolSchema
from app.agents.memory import AgentMemory
from app.agents.router import AgentCard, AgentRouter, DelegationResult
from app.agents.tool_protocol import ToolRegistry

logger = logging.getLogger(__name__)


# ============================================================================
# Delegation tracking
# ============================================================================

@dataclass
class DelegationStep:
    """Tracks a single delegation from orchestrator → specialist."""
    target_agent: str
    task: str
    result: str = ""
    success: bool = False
    tokens_used: int = 0
    duration_seconds: float = 0.0
    error: str = ""


@dataclass
class OrchestrationTrace:
    """Full trace of an orchestration run."""
    delegations: list[DelegationStep] = field(default_factory=list)
    total_delegations: int = 0
    total_agent_tokens: int = 0
    agents_used: list[str] = field(default_factory=list)


# ============================================================================
# Orchestrator Agent
# ============================================================================

class OrchestratorAgent(BaseAgent):
    """
    The top-level manager agent (Stripe Minions pattern).

    Unlike other agents that handle domain-specific tasks, the orchestrator:
    - Analyses ANY user request
    - Plans which specialists to invoke
    - Delegates via the ``delegate_task`` tool (agents-as-tools)
    - Synthesises a coherent response from all specialist outputs

    The orchestrator has NO domain expertise of its own. Its skill is
    *knowing who knows what* and *combining their outputs intelligently*.
    """

    name = "orchestrator"
    capabilities = [
        "orchestration",
        "task_decomposition",
        "delegation",
        "synthesis",
        "multi_agent_coordination",
    ]
    tags = [
        "manage", "coordinate", "help", "do", "handle",
        "figure out", "take care of", "assist",
    ]

    # The orchestrator uses ALL general tools PLUS the delegate_task tool.
    # The delegate_task tool is injected dynamically by the registry.
    default_tools = [
        "delegate_task",
        "get_current_datetime",
        "store_working_memory",
        "search_knowledge",
    ]

    default_system_prompt = """\
You are the Orchestrator — the top-level manager agent for Founder OS, an \
autonomous AI system that helps startup founders run their operations.

YOUR ROLE:
You are the single entry point for ALL user requests. You do NOT do \
specialist work yourself. Instead you:

1. ANALYSE the user's request to understand what they need
2. DECIDE which specialist agent(s) should handle it
3. DELEGATE by calling the `delegate_task` tool for each subtask
4. SYNTHESISE the results into one clear, coherent response

AVAILABLE SPECIALIST AGENTS:
- **planner**: Strategic planning, task management, prioritisation, OKRs, weekly plans
- **content**: Writing blog posts, tweets, newsletters, emails, landing page copy
- **research**: Market research, competitor analysis, data analysis, trend investigation
- **ops**: Operations monitoring, automation, scheduling, integration management
- **product**: Product management, feature planning, PRDs, user stories, roadmapping
- **support**: Customer support responses, FAQ, documentation, escalation

DECISION RULES:
- For simple, single-domain requests → delegate to ONE specialist
- For complex, cross-domain requests → delegate to MULTIPLE specialists, then synthesise
- For meta-questions about the system → answer directly (no delegation needed)
- For greetings or casual chat → respond directly with warmth
- When in doubt, delegate to **planner** first — it can further coordinate

HOW TO DELEGATE:
Call the `delegate_task` tool with:
- `agent_name`: which specialist to use (planner, content, research, ops, product, support)
- `task`: a clear, specific instruction for that specialist
- `context`: any relevant background the specialist needs

IMPORTANT:
- Write SPECIFIC tasks for each specialist — don't just forward the user's message verbatim
- Add context from the conversation so specialists have what they need
- When delegating to multiple agents, make each task self-contained
- After receiving delegation results, SYNTHESISE them — don't just paste outputs together
- Add your own connective analysis when combining multi-agent results
- Keep the final response focused on what the user actually asked for

SYNTHESIS GUIDELINES:
- Combine results logically, removing redundancy
- Highlight the most actionable takeaways
- Note any conflicts between specialist opinions
- Add a brief next-steps recommendation when appropriate
- Credit which specialist contributed which insight (e.g. "Based on market research...")

OUTPUT FORMAT:
- Use clear Markdown with headers and bullet points
- Lead with the most important information
- Keep it actionable — the founder's time is precious
"""

    def __init__(
        self,
        config: AgentConfig,
        memory: AgentMemory,
        llm: LLMProvider,
        tools: ToolRegistry,
        router: AgentRouter | None = None,
        event_bus: EventBus | None = None,
        approval_gate: "Any | None" = None,
        user_id: str = "",
    ) -> None:
        super().__init__(config, memory, llm, tools, router, event_bus, approval_gate, user_id)
        self._trace = OrchestrationTrace()

    async def run(
        self,
        user_input: str,
        *,
        query_embedding: list[float] | None = None,
        extra_context: str | None = None,
    ) -> AgentResult:
        """
        Execute the orchestration loop.

        Uses the standard ExecutionEngine (same as other agents), but
        with the delegate_task tool that enables agents-as-tools pattern.
        The LLM decides whether/when to delegate.
        """
        self._trace = OrchestrationTrace()

        # Emit orchestration.started
        if self.event_bus:
            await self.event_bus.publish(Event(
                type="orchestration.started",
                agent=self.name,
                data={"input_preview": user_input[:200]},
            ))

        # Run via the standard BaseAgent.run() — the delegate_task tool
        # is in the tool registry, so the LLM can call it naturally.
        result = await super().run(
            user_input,
            query_embedding=query_embedding,
            extra_context=extra_context,
        )

        # Enrich result with orchestration metadata
        result.delegations = [
            DelegationResult(
                from_agent="orchestrator",
                to_agent=d.target_agent,
                task=d.task,
                success=d.success,
                content=d.result[:500] if d.result else "",
                error=d.error,
                tokens_used=d.tokens_used,
                duration_seconds=d.duration_seconds,
            )
            for d in self._trace.delegations
        ]

        # Emit orchestration.completed
        if self.event_bus:
            await self.event_bus.publish(Event(
                type="orchestration.completed",
                agent=self.name,
                data={
                    "delegations": self._trace.total_delegations,
                    "agents_used": self._trace.agents_used,
                    "total_tokens": result.tokens_used + self._trace.total_agent_tokens,
                    "duration": result.duration_seconds,
                },
            ))

        return result

    async def after_run(self, user_input: str, result: AgentResult) -> None:
        """Persist orchestration summary to shared memory."""
        if result.content and self._trace.delegations:
            summary = {
                "user_request": user_input[:500],
                "agents_used": self._trace.agents_used,
                "delegations": self._trace.total_delegations,
                "summary": result.content[:1000],
            }
            await self.memory.save_to_shared(
                "last_orchestration",
                json.dumps(summary),
            )

    # ------------------------------------------------------------------
    # Delegation execution (called by the delegate_task tool)
    # ------------------------------------------------------------------

    async def execute_delegation(
        self,
        agent_name: str,
        task: str,
        context: str = "",
        *,
        user_id: Any = None,
        session_id: str | None = None,
    ) -> str:
        """
        Actually run a specialist agent. This is the implementation
        behind the ``delegate_task`` tool.

        Returns the specialist's response text (or an error message).
        """
        start = time.time()
        step = DelegationStep(target_agent=agent_name, task=task)

        try:
            # Build context for the specialist
            delegation_context = task
            if context:
                delegation_context += f"\n\n<context_from_orchestrator>\n{context}\n</context_from_orchestrator>"

            # Use the router to delegate
            if not self.router:
                step.error = "No router configured"
                step.success = False
                self._trace.delegations.append(step)
                return json.dumps({"error": step.error})

            from app.agents.router import AgentMessage

            message = AgentMessage(
                from_agent="orchestrator",
                to_agent=agent_name,
                task=delegation_context,
                context={"orchestrated": True},
            )

            delegation_result = await self.router.delegate(
                message,
                user_id=user_id,
                session_id=session_id,
            )

            duration = time.time() - start
            step.duration_seconds = duration
            step.tokens_used = delegation_result.tokens_used
            step.success = delegation_result.success

            if delegation_result.success:
                step.result = delegation_result.content
                self._trace.total_agent_tokens += delegation_result.tokens_used
                if agent_name not in self._trace.agents_used:
                    self._trace.agents_used.append(agent_name)
            else:
                step.error = delegation_result.error or "Delegation failed"

        except Exception as exc:
            step.error = str(exc)
            step.success = False
            logger.exception(
                "Orchestrator delegation to '%s' failed", agent_name,
            )

        self._trace.delegations.append(step)
        self._trace.total_delegations += 1

        # Return structured result for the LLM
        if step.success:
            return json.dumps({
                "agent": agent_name,
                "status": "success",
                "response": step.result,
                "tokens_used": step.tokens_used,
                "duration_seconds": round(step.duration_seconds, 2),
            })
        else:
            return json.dumps({
                "agent": agent_name,
                "status": "error",
                "error": step.error,
            })
