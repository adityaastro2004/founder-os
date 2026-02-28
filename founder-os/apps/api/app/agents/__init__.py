"""
Founder OS — Agent System (v2)
===============================
Multi-agent architecture with MCP tools, A2A routing, event bus,
and pluggable LLM providers (Ollama / Anthropic / OpenAI-compatible).

Usage:
    from app.agents import AgentRegistry

    registry = AgentRegistry(db_session, redis, settings)
    agent = await registry.get("planner", user_id=user.id)
    result = await agent.run("Plan next week's priorities")
"""

# Core
from app.agents.base import BaseAgent, AgentConfig, AgentResult

# Memory
from app.agents.memory import (
    AgentMemory,
    ConversationMemory,
    WorkingMemory,
    LongTermMemory,
    SharedMemory,
)

# LLM
from app.agents.llm import (
    LLMProvider,
    OllamaProvider,
    AnthropicProvider,
    OpenAICompatibleProvider,
    LLMMessage,
    LLMResponse,
    ToolSchema,
    create_llm_provider,
)

# Tools
from app.agents.tools import Tool, tool
from app.agents.tool_protocol import ToolProvider, LocalToolProvider, ToolRegistry, ToolResult
from app.agents.mcp_adapter import MCPStdioClient, MCPSSEClient, MCPServerConfig, create_mcp_client

# Execution
from app.agents.execution import ExecutionEngine, ExecutionResult, ExecutionStep

# A2A / Routing
from app.agents.router import AgentRouter, AgentCard, AgentMessage, DelegationResult

# Orchestrator
from app.agents.orchestrator import OrchestratorAgent, OrchestrationTrace

# Event Bus
from app.agents.event_bus import EventBus, Event

# Registry (top-level entry point)
from app.agents.registry import AgentRegistry

__all__ = [
    # Core
    "BaseAgent",
    "AgentConfig",
    "AgentResult",
    # Memory
    "AgentMemory",
    "ConversationMemory",
    "WorkingMemory",
    "LongTermMemory",
    "SharedMemory",
    # LLM
    "LLMProvider",
    "OllamaProvider",
    "AnthropicProvider",
    "OpenAICompatibleProvider",
    "LLMMessage",
    "LLMResponse",
    "ToolSchema",
    "create_llm_provider",
    # Tools
    "Tool",
    "tool",
    "ToolProvider",
    "LocalToolProvider",
    "ToolRegistry",
    "ToolResult",
    "MCPStdioClient",
    "MCPSSEClient",
    "MCPServerConfig",
    "create_mcp_client",
    # Execution
    "ExecutionEngine",
    "ExecutionResult",
    "ExecutionStep",
    # A2A
    "AgentRouter",
    "AgentCard",
    "AgentMessage",
    "DelegationResult",
    # Orchestrator
    "OrchestratorAgent",
    "OrchestrationTrace",
    # Event Bus
    "EventBus",
    "Event",
    # Registry
    "AgentRegistry",
]
