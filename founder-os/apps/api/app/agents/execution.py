"""
Founder OS — Execution Engine
================================
Step-based execution engine that powers the agentic loop.

Decouples the execution logic from the BaseAgent, making it testable,
composable, and extensible. Handles:
  - LLM calls (via LLMProvider)
  - Tool calls (via ToolRegistry — supports MCP)
  - Agent delegations (via AgentRouter — A2A)
  - Memory operations
  - Retries, timeouts, cost tracking

Architecture:
  ┌─────────────────────────────────────────────┐
  │              ExecutionEngine                  │
  │                                               │
  │  while not done:                              │
  │    1. Call LLM with messages + tools          │
  │    2. If tool_calls → execute via ToolRegistry│
  │    3. If delegation → route via AgentRouter   │
  │    4. Append results → loop                   │
  │                                               │
  │  Tracks: steps, tokens, cost, duration        │
  └─────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from app.agents.llm import (
    LLMMessage,
    LLMProvider,
    LLMResponse,
    Role,
    ToolCallRequest,
    ToolSchema,
)
from app.agents.tool_protocol import ToolRegistry, ToolResult

if TYPE_CHECKING:
    from app.agents.approval import ApprovalGate
    from app.agents.event_bus import EventBus

logger = logging.getLogger(__name__)

# Tool output re-enters the message list and is re-sent on EVERY subsequent
# round of the loop — an unbounded result (crawled page, busy calendar dump)
# multiplies across rounds. ~2k tokens is enough for any tool to act on.
_TOOL_RESULT_MAX_CHARS = 8000


def _clip_tool_result(content: str) -> str:
    """Truncate oversized tool output before it joins the conversation."""
    if len(content) <= _TOOL_RESULT_MAX_CHARS:
        return content
    dropped = len(content) - _TOOL_RESULT_MAX_CHARS
    return (
        content[:_TOOL_RESULT_MAX_CHARS]
        + f"\n…[tool output truncated: {dropped} chars dropped. "
        "Re-call with narrower arguments if you need the rest.]"
    )


# ============================================================================
# Execution data types
# ============================================================================

@dataclass
class ExecutionStep:
    """A single step in the execution trace."""
    step_type: str      # "llm_call" | "tool_call" | "delegation" | "error"
    agent: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    result: str = ""
    tokens: int = 0
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class ExecutionResult:
    """The output of a complete agent execution."""
    content: str
    steps: list[ExecutionStep] = field(default_factory=list)
    total_tokens: int = 0
    total_tool_calls: int = 0
    total_delegations: int = 0
    duration_seconds: float = 0.0
    stop_reason: str = ""
    model: str = ""
    cost_usd: float = 0.0
    pending_approvals: list[dict[str, Any]] = field(default_factory=list)

    @property
    def tool_calls_log(self) -> list[dict[str, Any]]:
        return [
            s.detail for s in self.steps
            if s.step_type == "tool_call"
        ]


# ============================================================================
# Cost estimator (rough per-token pricing)
# ============================================================================

_COST_PER_1K: dict[str, tuple[float, float]] = {
    # (input_per_1k, output_per_1k)
    "claude-sonnet-4-20250514": (0.003, 0.015),
    "claude-haiku-4-20250514": (0.0008, 0.004),
    "gpt-4o-mini": (0.00015, 0.0006),
    # Ollama / local models = free
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = _COST_PER_1K.get(model)
    if not rates:
        return 0.0  # free / unknown
    return (input_tokens / 1000) * rates[0] + (output_tokens / 1000) * rates[1]


# ============================================================================
# Execution Engine
# ============================================================================

class ExecutionEngine:
    """
    Runs the agentic loop: LLM → tool calls → LLM → … → final answer.

    This is the core execution logic, decoupled from BaseAgent so it can
    be tested independently and reused across different agent types.
    """

    def __init__(
        self,
        llm: LLMProvider,
        tools: ToolRegistry,
        *,
        max_rounds: int = 15,
        parallel_tool_calls: bool = True,
        approval_gate: "ApprovalGate | None" = None,
        user_id: str = "",
        agent_name: str = "",
        event_bus: "EventBus | None" = None,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.max_rounds = max_rounds
        self.parallel_tool_calls = parallel_tool_calls
        self.approval_gate = approval_gate
        self.user_id = user_id
        self._agent_name = agent_name
        self._event_bus = event_bus

    async def run(
        self,
        messages: list[LLMMessage],
        *,
        system: str = "",
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        agent_name: str = "",
    ) -> ExecutionResult:
        """
        Execute the full agentic loop.

        Args:
            messages: Conversation history (user messages, etc.)
            system: System prompt
            model: Model override
            temperature: Sampling temperature
            max_tokens: Max tokens per LLM call
            agent_name: For logging / tracing
        """
        start_time = time.time()
        steps: list[ExecutionStep] = []
        total_tokens = 0
        total_input_tokens = 0
        total_output_tokens = 0
        final_text = ""
        stop_reason = ""
        model_used = model or ""
        pending_approvals: list[dict[str, Any]] = []

        # Get available tool schemas
        tool_schemas = await self.tools.list_tools()

        for round_num in range(self.max_rounds):
            # -- Step: LLM call ---------------------------------
            llm_start = time.time()
            try:
                response = await self.llm.generate(
                    messages,
                    system=system,
                    tools=tool_schemas if tool_schemas else None,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as exc:
                logger.exception("LLM call failed for agent '%s'", agent_name)
                steps.append(ExecutionStep(
                    step_type="error",
                    agent=agent_name,
                    detail={"error": str(exc), "round": round_num},
                ))
                # Give the user a clear message when rate-limited
                if "429" in str(exc) or "rate" in str(exc).lower():
                    final_text = (
                        "I'm temporarily rate-limited by the AI provider. "
                        "Please wait a minute and try again."
                    )
                else:
                    # Never return a silent-empty "completed" result — surface the
                    # failure so callers/UIs see what actually happened.
                    final_text = (
                        f"Agent '{agent_name}' could not get a response from the "
                        f"LLM provider ({type(exc).__name__}: {exc}). "
                        "Check the LLM provider configuration and try again."
                    )
                break

            llm_duration = (time.time() - llm_start) * 1000
            total_tokens += response.usage.total
            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens
            model_used = response.model or model_used
            stop_reason = response.stop_reason

            steps.append(ExecutionStep(
                step_type="llm_call",
                agent=agent_name,
                detail={
                    "round": round_num,
                    "model": model_used,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "tool_calls_requested": len(response.tool_calls),
                },
                tokens=response.usage.total,
                duration_ms=llm_duration,
            ))

            # -- If no tool calls, we're done --------------------
            if not response.tool_calls:
                final_text = response.content
                break

            # -- Append assistant message with tool calls --------
            messages.append(LLMMessage(
                role=Role.ASSISTANT,
                content=response.content,
                tool_calls=response.tool_calls,
            ))

            # -- Step: Execute tool calls (with approval gate) --
            tool_results, new_pending = await self._execute_tool_calls(
                response.tool_calls,
                agent_name=agent_name,
                steps=steps,
            )
            pending_approvals.extend(new_pending)

            # -- Append tool results as messages (clipped — see above) --
            for tr in tool_results:
                messages.append(LLMMessage(
                    role=Role.TOOL_RESULT,
                    content=_clip_tool_result(tr.content),
                    tool_call_id=tr.tool_call_id,
                ))

        else:
            # Exceeded max rounds
            logger.warning(
                "Agent '%s' hit max tool rounds (%d)",
                agent_name, self.max_rounds,
            )
            if not final_text:
                final_text = "(Agent reached maximum execution rounds)"
            stop_reason = "max_rounds"

        duration = time.time() - start_time
        cost = _estimate_cost(model_used, total_input_tokens, total_output_tokens)

        return ExecutionResult(
            content=final_text,
            steps=steps,
            total_tokens=total_tokens,
            total_tool_calls=sum(1 for s in steps if s.step_type == "tool_call"),
            duration_seconds=duration,
            stop_reason=stop_reason,
            model=model_used,
            cost_usd=cost,
            pending_approvals=pending_approvals,
        )

    # -- Tool execution ---------------------------------------------------

    async def _execute_tool_calls(
        self,
        tool_calls: list[ToolCallRequest],
        agent_name: str,
        steps: list[ExecutionStep],
    ) -> tuple[list[ToolResult], list[dict[str, Any]]]:
        """
        Execute tool calls with approval gate checks.

        Returns:
            (results, pending_approvals) — results for each tool call,
            plus a list of any pending approval dicts created.
        """
        results: list[ToolResult] = []
        pending: list[dict[str, Any]] = []

        for tc in tool_calls:
            # -- Approval gate check --
            if self.approval_gate and self.user_id:
                decision = await self.approval_gate.check(
                    user_id=self.user_id,
                    tool_name=tc.name,
                    arguments=tc.arguments,
                    agent_name=agent_name,
                    session_id="",
                )

                if not decision.approved:
                    # Tool call needs user approval — return a placeholder result
                    approval_info = (
                        decision.pending_approval.to_dict()
                        if decision.pending_approval
                        else {}
                    )
                    pending.append(approval_info)

                    results.append(ToolResult(
                        tool_call_id=tc.id,
                        content=json.dumps({
                            "status": "pending_approval",
                            "approval_id": approval_info.get("id", ""),
                            "message": decision.reason,
                            "description": approval_info.get("description", ""),
                        }),
                        is_error=False,
                    ))

                    steps.append(ExecutionStep(
                        step_type="approval_required",
                        agent=agent_name,
                        detail={
                            "tool": tc.name,
                            "arguments": tc.arguments,
                            "approval_id": approval_info.get("id", ""),
                            "risk_level": approval_info.get("risk_level", ""),
                        },
                        result=decision.reason,
                    ))

                    logger.info(
                        "Agent '%s' tool '%s' → PENDING APPROVAL (id=%s)",
                        agent_name, tc.name, approval_info.get("id", ""),
                    )
                    continue

                # If auto-approved, log it
                if decision.auto_approved:
                    logger.info(
                        "Agent '%s' tool '%s' → auto-approved (always_allow)",
                        agent_name, tc.name,
                    )

            # -- Emit tool.called event --
            args = tc.arguments or {}
            if self._event_bus:
                from app.agents.event_bus import Event
                await self._event_bus.publish(Event(
                    type="tool.called",
                    agent=agent_name,
                    data={
                        "tool_name": tc.name,
                        "arguments": {k: str(v)[:200] for k, v in args.items()},
                        "user_id": str(self.user_id),
                    },
                ))

            # -- Execute the tool --
            try:
                result = await self.tools.call_tool(
                    tc.name, args, tc.id,
                )
            except Exception as exc:
                logger.exception(
                    "Agent '%s' tool '%s' crashed: %s",
                    agent_name, tc.name, exc,
                )
                result = ToolResult(
                    tool_call_id=tc.id,
                    content=f"Tool error: {type(exc).__name__}: {exc}",
                    is_error=True,
                    duration_ms=0.0,
                )
            results.append(result)

            # -- Emit tool.result event --
            if self._event_bus:
                from app.agents.event_bus import Event
                await self._event_bus.publish(Event(
                    type="tool.result",
                    agent=agent_name,
                    data={
                        "tool_name": tc.name,
                        "is_error": result.is_error,
                        "duration_ms": round(result.duration_ms, 1),
                        "result_preview": result.content[:300],
                        "user_id": str(self.user_id),
                    },
                ))

            # Log tool call step
            steps.append(ExecutionStep(
                step_type="tool_call",
                agent=agent_name,
                detail={
                    "tool": tc.name,
                    "arguments": args,
                    "is_error": result.is_error,
                },
                result=result.content[:500],
                duration_ms=result.duration_ms,
            ))

            logger.info(
                "Agent '%s' tool call: %s → %s (%.0fms)",
                agent_name, tc.name,
                "error" if result.is_error else "ok",
                result.duration_ms,
            )

        return results, pending
