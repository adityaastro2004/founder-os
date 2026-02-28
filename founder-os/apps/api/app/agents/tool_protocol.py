"""
Founder OS — MCP-Compatible Tool Protocol
===========================================
Standardised tool interface inspired by the Model Context Protocol (MCP).

Architecture:
  ┌──────────────────────────────────────────────────────┐
  │                    ToolRegistry                       │
  │  ┌─────────────┐ ┌──────────────┐ ┌──────────────┐  │
  │  │ LocalTools   │ │  MCPServer1  │ │  MCPServer2  │  │
  │  │ (@tool deco) │ │ (external)   │ │ (external)   │  │
  │  └──────┬──────┘ └──────┬───────┘ └──────┬───────┘  │
  │         └───────────────┼────────────────┘           │
  │                   unified interface                   │
  │           list_tools()  /  call_tool()               │
  └──────────────────────────────────────────────────────┘

Each provider implements ``ToolProvider`` — a simple ABC with two methods.
The ``ToolRegistry`` aggregates multiple providers and presents a unified
list of available tools to the agent / LLM.
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.agents.llm import ToolSchema
from app.agents.tools import Tool as InternalTool, get_tool, list_tools as list_internal_tools

logger = logging.getLogger(__name__)


# ============================================================================
# Core data types
# ============================================================================

@dataclass
class ToolResult:
    """Standardised result from calling any tool."""
    tool_call_id: str
    content: str
    is_error: bool = False
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallRecord:
    """Audit record of a tool invocation."""
    tool_name: str
    arguments: dict[str, Any]
    result: ToolResult
    provider: str
    timestamp: float = field(default_factory=time.time)


# ============================================================================
# Abstract Tool Provider (MCP-compatible interface)
# ============================================================================

class ToolProvider(ABC):
    """
    A source of callable tools.
    Mirrors the MCP server interface: list + call.
    """

    provider_name: str = "base"

    @abstractmethod
    async def list_tools(self) -> list[ToolSchema]:
        """Return schemas for all tools this provider offers."""
        ...

    @abstractmethod
    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        tool_call_id: str = "",
    ) -> ToolResult:
        """Execute a tool by name and return the result."""
        ...

    async def health_check(self) -> bool:
        """Optional health probe."""
        return True


# ============================================================================
# Local Tool Provider — wraps the @tool decorator catalog
# ============================================================================

class LocalToolProvider(ToolProvider):
    """
    Provides tools registered via the ``@tool`` decorator in ``tools.py``.
    This is the main provider for built-in Founder OS tools.
    """

    provider_name = "local"

    def __init__(self, allowed_tools: list[str] | None = None) -> None:
        """
        Args:
            allowed_tools: If set, only expose these tool names.
                           If None, expose all registered tools.
        """
        self._allowed = set(allowed_tools) if allowed_tools else None

    async def list_tools(self) -> list[ToolSchema]:
        all_names = list_internal_tools()
        schemas: list[ToolSchema] = []
        for name in all_names:
            if self._allowed and name not in self._allowed:
                continue
            t = get_tool(name)
            schemas.append(ToolSchema(
                name=t.name,
                description=t.description,
                parameters=t.parameters,
            ))
        return schemas

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        tool_call_id: str = "",
    ) -> ToolResult:
        start = time.monotonic()
        try:
            t = get_tool(name)
            result_str = await t.execute(**arguments)
            duration = (time.monotonic() - start) * 1000
            return ToolResult(
                tool_call_id=tool_call_id,
                content=result_str,
                is_error=False,
                duration_ms=duration,
            )
        except Exception as exc:
            duration = (time.monotonic() - start) * 1000
            logger.exception("Local tool '%s' failed", name)
            return ToolResult(
                tool_call_id=tool_call_id,
                content=json.dumps({"error": str(exc)}),
                is_error=True,
                duration_ms=duration,
            )


# ============================================================================
# Tool Registry — aggregates multiple providers
# ============================================================================

class ToolRegistry:
    """
    Central registry that aggregates tools from multiple providers
    (local, MCP servers, etc.) and presents a unified interface.
    """

    def __init__(self) -> None:
        self._providers: list[ToolProvider] = []
        self._tool_to_provider: dict[str, ToolProvider] = {}
        self._schema_cache: list[ToolSchema] | None = None

    def add_provider(self, provider: ToolProvider) -> None:
        """Register a tool provider."""
        self._providers.append(provider)
        self._schema_cache = None  # invalidate

    async def refresh(self) -> None:
        """Re-scan all providers and rebuild the tool→provider map."""
        self._tool_to_provider.clear()
        all_schemas: list[ToolSchema] = []

        for provider in self._providers:
            try:
                schemas = await provider.list_tools()
                for s in schemas:
                    if s.name in self._tool_to_provider:
                        logger.warning(
                            "Tool '%s' from '%s' shadows existing tool from '%s'",
                            s.name,
                            provider.provider_name,
                            self._tool_to_provider[s.name].provider_name,
                        )
                    self._tool_to_provider[s.name] = provider
                    all_schemas.append(s)
            except Exception:
                logger.exception(
                    "Failed to list tools from provider '%s'",
                    provider.provider_name,
                )

        self._schema_cache = all_schemas

    async def list_tools(self) -> list[ToolSchema]:
        """Return all available tool schemas from all providers."""
        if self._schema_cache is None:
            await self.refresh()
        return self._schema_cache or []

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        tool_call_id: str = "",
    ) -> ToolResult:
        """Route a tool call to the correct provider."""
        if self._schema_cache is None:
            await self.refresh()

        provider = self._tool_to_provider.get(name)
        if provider is None:
            return ToolResult(
                tool_call_id=tool_call_id,
                content=json.dumps({
                    "error": f"Tool '{name}' not found. Available: {list(self._tool_to_provider.keys())}",
                }),
                is_error=True,
            )

        logger.info("Calling tool '%s' via provider '%s'", name, provider.provider_name)
        result = await provider.call_tool(name, arguments, tool_call_id)

        return result

    async def call_tools_parallel(
        self,
        calls: list[dict[str, Any]],
    ) -> list[ToolResult]:
        """
        Execute multiple tool calls concurrently.

        Args:
            calls: List of dicts with keys: name, arguments, tool_call_id
        """
        import asyncio
        tasks = [
            self.call_tool(
                name=c["name"],
                arguments=c["arguments"],
                tool_call_id=c.get("tool_call_id", ""),
            )
            for c in calls
        ]
        return await asyncio.gather(*tasks)

    @property
    def tool_names(self) -> list[str]:
        return list(self._tool_to_provider.keys())

    @property
    def provider_count(self) -> int:
        return len(self._providers)

    # ------------------------------------------------------------------
    # Runtime tool override (for agents-as-tools / Minions pattern)
    # ------------------------------------------------------------------

    def override_tool_impl(
        self,
        tool_name: str,
        impl: Any,
    ) -> None:
        """
        Replace a tool's implementation at runtime.

        This is used by the Orchestrator to bind the ``delegate_task``
        placeholder to an actual delegation closure that has access to
        the orchestrator instance, user_id, and session_id.

        The override installs a ``ClosureToolProvider`` that intercepts
        calls to ``tool_name`` and routes them to ``impl``.

        Args:
            tool_name: Name of the tool to override.
            impl: An async callable matching the tool's signature.
        """
        closure_provider = _ClosureToolProvider(tool_name, impl)
        # The closure provider must appear *before* the local provider
        # in the lookup map so it shadows the placeholder.
        self._tool_to_provider[tool_name] = closure_provider
        logger.info("Tool '%s' overridden with runtime closure", tool_name)


class _ClosureToolProvider(ToolProvider):
    """
    A thin ToolProvider that wraps a single async callable.

    Used to inject runtime closures (e.g. delegate_task bound to
    the orchestrator) into the tool registry without modifying the
    global @tool catalog.
    """

    provider_name = "closure"

    def __init__(self, tool_name: str, impl: Any) -> None:
        self._tool_name = tool_name
        self._impl = impl

    async def list_tools(self) -> list[ToolSchema]:
        # Schema already exists from the @tool decorator; we only
        # override the execution path.
        return []

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        tool_call_id: str = "",
    ) -> ToolResult:
        start = time.monotonic()
        try:
            result_str = await self._impl(**arguments)
            duration = (time.monotonic() - start) * 1000
            return ToolResult(
                tool_call_id=tool_call_id,
                content=result_str,
                is_error=False,
                duration_ms=duration,
            )
        except Exception as exc:
            duration = (time.monotonic() - start) * 1000
            logger.exception("Closure tool '%s' failed", name)
            return ToolResult(
                tool_call_id=tool_call_id,
                content=json.dumps({"error": str(exc)}),
                is_error=True,
                duration_ms=duration,
            )
