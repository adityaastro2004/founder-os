"""
Founder OS — Tool System
=========================
Provides a @tool decorator and Tool dataclass that agents use to interact
with the outside world (search, write content, check analytics, etc.).

Tools are defined as plain async functions, decorated with @tool, and
auto-registered into a global catalog. Each agent declares which tool
*names* it can use, and the BaseAgent resolves them at runtime.

Example:
    @tool(
        name="web_search",
        description="Search the web for a query and return results.",
    )
    async def web_search(query: str, num_results: int = 5) -> str:
        ...
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, get_type_hints


# ============================================================================
# Tool dataclass — serialises to Anthropic-compatible tool schema
# ============================================================================

@dataclass(frozen=True, slots=True)
class Tool:
    """A callable capability that an agent can invoke."""

    name: str
    description: str
    fn: Callable[..., Awaitable[Any]]
    parameters: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Anthropic tool-use format
    # ------------------------------------------------------------------
    def to_anthropic_schema(self) -> dict[str, Any]:
        """Return the tool definition expected by the Anthropic messages API."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

    async def execute(self, **kwargs: Any) -> str:
        """Run the underlying function and return a JSON-safe string result."""
        result = await self.fn(**kwargs)
        if isinstance(result, str):
            return result
        return json.dumps(result, default=str)


# ============================================================================
# Global tool catalog
# ============================================================================

_TOOL_CATALOG: dict[str, Tool] = {}


def get_tool(name: str) -> Tool:
    if name not in _TOOL_CATALOG:
        raise KeyError(f"Tool '{name}' not found. Registered: {list(_TOOL_CATALOG)}")
    return _TOOL_CATALOG[name]


def get_tools(names: list[str]) -> list[Tool]:
    return [get_tool(n) for n in names]


def list_tools() -> list[str]:
    return list(_TOOL_CATALOG.keys())


# ============================================================================
# @tool decorator
# ============================================================================

def _build_json_schema_from_sig(fn: Callable) -> dict[str, Any]:
    """Derive a JSON-Schema-style ``input_schema`` from function signature."""
    sig = inspect.signature(fn)
    hints = get_type_hints(fn)

    properties: dict[str, Any] = {}
    required: list[str] = []

    _PY_TO_JSON = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    for name, param in sig.parameters.items():
        # skip self / cls
        if name in ("self", "cls"):
            continue

        hint = hints.get(name, str)
        json_type = _PY_TO_JSON.get(hint, "string")
        prop: dict[str, Any] = {"type": json_type}

        if param.default is inspect.Parameter.empty:
            required.append(name)
        else:
            prop["default"] = param.default

        properties[name] = prop

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def tool(
    name: str | None = None,
    description: str = "",
    parameters: dict[str, Any] | None = None,
) -> Callable:
    """
    Decorator that registers an async function as an agent tool.

    Usage::

        @tool(name="web_search", description="Search the web")
        async def web_search(query: str, num_results: int = 5) -> str:
            ...
    """
    def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        tool_name = name or fn.__name__
        schema = parameters or _build_json_schema_from_sig(fn)

        t = Tool(
            name=tool_name,
            description=description or fn.__doc__ or "",
            fn=fn,
            parameters=schema,
        )
        _TOOL_CATALOG[tool_name] = t
        # Attach metadata so the raw function still works normally
        fn._tool = t  # type: ignore[attr-defined]
        return fn

    return decorator
