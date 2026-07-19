"""Shared service-free harness for BaseAgent prompt-contract tests (017/020).

Doubles extracted from test_agent_history_prompt.py (task 017) so the chat
memory suite (task 020) can reuse them: stub LLM provider, recorder in place
of the ExecutionEngine, and no-op profile/memory context loaders — no server,
DB, Redis, or LLM.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import AgentConfig, BaseAgent
from app.agents.execution import ExecutionResult
from app.agents.llm import LLMMessage, LLMProvider, LLMResponse, ToolSchema
from app.agents.memory import AgentMemory, ConversationMemory
from app.agents.tool_protocol import ToolRegistry


class StubLLM(LLMProvider):
    """Provider that never gets called — the engine is replaced too.

    ``calls`` counts generate() invocations (task 020 AC-5: 0 completions).
    """

    provider_name = "stub"

    def __init__(self) -> None:
        self.calls = 0

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        system: str = "",
        tools: list[ToolSchema] | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop_sequences: list[str] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        self.calls += 1
        return LLMResponse(content="stub", model=model or "stub-model")


class RecorderEngine:
    """Replaces BaseAgent._engine; captures the exact LLM-call inputs."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def run(self, messages: list[LLMMessage], *, system: str = "", **kwargs: Any) -> ExecutionResult:
        self.calls.append({"messages": list(messages), "system": system, "kwargs": kwargs})
        return ExecutionResult(content="canned reply", stop_reason="end_turn", model="stub-model")


class EchoAgent(BaseAgent):
    """Minimal concrete agent — the contract under test lives in BaseAgent."""

    name = "echo"
    default_system_prompt = "You are Echo, a test agent for the founder's business."


def make_agent(
    prior_turns: list[tuple[str, str]] | None = None,
) -> tuple[EchoAgent, RecorderEngine]:
    """Build a service-free agent with `prior_turns` pre-hydrated (like
    agent_routes._load_session_history does) and a recorder engine."""
    conversation = ConversationMemory()
    # working/long_term are never touched: build_context is stubbed below.
    memory = AgentMemory(conversation=conversation, working=None, long_term=None)  # type: ignore[arg-type]
    agent = EchoAgent(
        config=AgentConfig(name="echo", display_name="Echo"),
        memory=memory,
        llm=StubLLM(),
        tools=ToolRegistry(),
        event_bus=None,
        embedder=None,
    )

    async def _empty(*args: Any, **kwargs: Any) -> str:
        return ""

    # No DB/Redis: profile loaders and memory context return nothing.
    agent._load_founder_profile_context = _empty  # type: ignore[method-assign]
    agent._load_user_profile_context = _empty  # type: ignore[method-assign]
    agent.memory.build_context = _empty  # type: ignore[method-assign]

    engine = RecorderEngine()
    agent._engine = engine  # type: ignore[assignment]

    for role, content in prior_turns or []:
        conversation.add(role, content)
    return agent, engine
