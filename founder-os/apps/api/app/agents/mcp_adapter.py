"""
Founder OS — MCP Adapter
==========================
Bridges external MCP-compatible tool servers into the ToolRegistry.

Supports two transports:
  - **stdio** — spawn a subprocess, communicate via stdin/stdout JSON-RPC
  - **SSE**   — connect to a remote HTTP+SSE MCP server

This implements a minimal MCP client that speaks JSON-RPC 2.0 and
supports the core MCP methods: ``initialize``, ``tools/list``, ``tools/call``.

No external dependencies beyond httpx (already installed).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.agents.llm import ToolSchema
from app.agents.tool_protocol import ToolProvider, ToolResult

logger = logging.getLogger(__name__)


# ============================================================================
# MCP Server descriptor
# ============================================================================

@dataclass
class MCPServerConfig:
    """Configuration for an external MCP tool server."""
    name: str
    transport: str = "stdio"           # "stdio" | "sse"
    command: str | None = None         # for stdio: the command to spawn
    args: list[str] = field(default_factory=list)
    url: str | None = None             # for SSE: the server URL
    env: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    timeout: float = 30.0


# ============================================================================
# JSON-RPC helpers
# ============================================================================

def _jsonrpc_request(method: str, params: dict | None = None) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": uuid.uuid4().hex[:8],
        "method": method,
        "params": params or {},
    }


def _parse_jsonrpc_response(data: dict) -> Any:
    if "error" in data:
        err = data["error"]
        raise RuntimeError(f"MCP error {err.get('code', '?')}: {err.get('message', 'unknown')}")
    return data.get("result")


# ============================================================================
# MCP Client — stdio transport
# ============================================================================

class MCPStdioClient(ToolProvider):
    """
    Connects to an MCP server via subprocess stdio.
    The server process is spawned on first use and kept alive.
    """

    provider_name = "mcp_stdio"

    def __init__(self, config: MCPServerConfig) -> None:
        self._config = config
        self.provider_name = f"mcp:{config.name}"
        self._process: asyncio.subprocess.Process | None = None
        self._tools_cache: list[ToolSchema] | None = None
        self._lock = asyncio.Lock()

    async def _ensure_started(self) -> None:
        if self._process is not None and self._process.returncode is None:
            return
        async with self._lock:
            if self._process is not None and self._process.returncode is None:
                return
            cmd = self._config.command
            if not cmd:
                raise ValueError(f"No command specified for MCP stdio server '{self._config.name}'")

            logger.info("Starting MCP server '%s': %s %s", self._config.name, cmd, self._config.args)
            self._process = await asyncio.create_subprocess_exec(
                cmd, *self._config.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**dict(__import__("os").environ), **self._config.env} if self._config.env else None,
            )

            # Send initialize
            await self._send(_jsonrpc_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "founder-os", "version": "1.0.0"},
            }))

    async def _send(self, request: dict) -> Any:
        proc = self._process
        if proc is None or proc.stdin is None or proc.stdout is None:
            raise RuntimeError("MCP process not started")

        payload = json.dumps(request) + "\n"
        proc.stdin.write(payload.encode())
        await proc.stdin.drain()

        line = await asyncio.wait_for(
            proc.stdout.readline(),
            timeout=self._config.timeout,
        )
        if not line:
            raise RuntimeError("MCP process closed stdout")

        data = json.loads(line.decode())
        return _parse_jsonrpc_response(data)

    async def list_tools(self) -> list[ToolSchema]:
        await self._ensure_started()
        result = await self._send(_jsonrpc_request("tools/list"))
        tools_data = result.get("tools", []) if isinstance(result, dict) else []
        self._tools_cache = [
            ToolSchema(
                name=t["name"],
                description=t.get("description", ""),
                parameters=t.get("inputSchema", {"type": "object", "properties": {}}),
            )
            for t in tools_data
        ]
        return self._tools_cache

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        tool_call_id: str = "",
    ) -> ToolResult:
        await self._ensure_started()
        try:
            result = await self._send(_jsonrpc_request("tools/call", {
                "name": name,
                "arguments": arguments,
            }))
            content_parts = result.get("content", []) if isinstance(result, dict) else []
            text_parts = [
                c.get("text", "") for c in content_parts
                if isinstance(c, dict) and c.get("type") == "text"
            ]
            return ToolResult(
                tool_call_id=tool_call_id,
                content="\n".join(text_parts) or json.dumps(result),
                is_error=bool(result.get("isError")) if isinstance(result, dict) else False,
            )
        except Exception as exc:
            return ToolResult(
                tool_call_id=tool_call_id,
                content=json.dumps({"error": str(exc)}),
                is_error=True,
            )

    async def health_check(self) -> bool:
        try:
            await self._ensure_started()
            return self._process is not None and self._process.returncode is None
        except Exception:
            return False

    async def close(self) -> None:
        if self._process and self._process.returncode is None:
            self._process.terminate()
            await self._process.wait()


# ============================================================================
# MCP Client — SSE transport
# ============================================================================

class MCPSSEClient(ToolProvider):
    """
    Connects to a remote MCP server via HTTP + SSE.
    Sends JSON-RPC requests via HTTP POST, optionally listens to SSE stream.
    """

    provider_name = "mcp_sse"

    def __init__(self, config: MCPServerConfig) -> None:
        self._config = config
        self.provider_name = f"mcp:{config.name}"
        self._client = httpx.AsyncClient(
            base_url=config.url or "",
            headers=config.headers,
            timeout=config.timeout,
        )
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        resp = await self._client.post("/", json=_jsonrpc_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "founder-os", "version": "1.0.0"},
        }))
        resp.raise_for_status()
        self._initialized = True

    async def list_tools(self) -> list[ToolSchema]:
        await self._ensure_initialized()
        resp = await self._client.post("/", json=_jsonrpc_request("tools/list"))
        resp.raise_for_status()
        result = _parse_jsonrpc_response(resp.json())
        tools_data = result.get("tools", []) if isinstance(result, dict) else []
        return [
            ToolSchema(
                name=t["name"],
                description=t.get("description", ""),
                parameters=t.get("inputSchema", {"type": "object", "properties": {}}),
            )
            for t in tools_data
        ]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        tool_call_id: str = "",
    ) -> ToolResult:
        await self._ensure_initialized()
        try:
            resp = await self._client.post("/", json=_jsonrpc_request("tools/call", {
                "name": name,
                "arguments": arguments,
            }))
            resp.raise_for_status()
            result = _parse_jsonrpc_response(resp.json())
            content_parts = result.get("content", []) if isinstance(result, dict) else []
            text_parts = [
                c.get("text", "") for c in content_parts
                if isinstance(c, dict) and c.get("type") == "text"
            ]
            return ToolResult(
                tool_call_id=tool_call_id,
                content="\n".join(text_parts) or json.dumps(result),
                is_error=bool(result.get("isError")) if isinstance(result, dict) else False,
            )
        except Exception as exc:
            return ToolResult(
                tool_call_id=tool_call_id,
                content=json.dumps({"error": str(exc)}),
                is_error=True,
            )

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get("/health")
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()


# ============================================================================
# Factory
# ============================================================================

def create_mcp_client(config: MCPServerConfig) -> ToolProvider:
    """Create the appropriate MCP client for a server config."""
    if config.transport == "stdio":
        return MCPStdioClient(config)
    elif config.transport == "sse":
        return MCPSSEClient(config)
    else:
        raise ValueError(f"Unknown MCP transport: {config.transport}")
