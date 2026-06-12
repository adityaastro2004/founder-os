"""
Founder OS — LLM Provider Abstraction
=======================================
Unified interface for multiple LLM backends.

Supported providers:
  - **Ollama**  (free, local)  — default, no API key needed
  - **Anthropic** — Claude models via the anthropic SDK
  - **OpenAI-compatible** — any provider with an OpenAI-format chat API
    (vLLM, Together, Groq, LM Studio, etc.)

Every provider implements ``generate()`` which accepts a provider-agnostic
message format and returns a unified ``LLMResponse``.
"""

from __future__ import annotations

import json
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ============================================================================
# Unified message / response types (provider-agnostic)
# ============================================================================

class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL_RESULT = "tool_result"


@dataclass
class ToolCallRequest:
    """A tool call the LLM wants to make."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ContentBlock:
    """A block of content — text or tool_use."""
    type: str  # "text" | "tool_use"
    text: str | None = None
    tool_call: ToolCallRequest | None = None


@dataclass
class LLMMessage:
    """Provider-agnostic message."""
    role: Role
    content: str | list[ContentBlock] = ""
    tool_call_id: str | None = None        # when role == TOOL_RESULT
    tool_calls: list[ToolCallRequest] | None = None  # when role == ASSISTANT
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class ToolSchema:
    """JSON-Schema tool definition for LLM function calling."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema object


@dataclass
class LLMResponse:
    """Unified response from any LLM provider."""
    content: str
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)
    stop_reason: str = ""      # "end_turn" | "tool_use" | "max_tokens" | ...
    model: str = ""
    raw: Any = None            # provider-specific raw response


# ============================================================================
# Abstract provider
# ============================================================================

class LLMProvider(ABC):
    """Base class for all LLM providers."""

    provider_name: str = "base"

    @abstractmethod
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
        """Generate a completion."""
        ...

    async def health_check(self) -> bool:
        """Return True if the provider is reachable."""
        return True


# ============================================================================
# Ollama (FREE — local)
# ============================================================================

class OllamaProvider(LLMProvider):
    """
    Ollama running locally at http://localhost:11434.
    Supports tool calling on compatible models (llama3.1, mistral, etc.).
    Completely free — no API key, no rate limits.
    """

    provider_name = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        default_model: str = "llama3.1:8b",
        timeout: float = 300.0,
    ) -> None:
        # 300s: local models pay a long prompt-eval cost on orchestrator-sized
        # prompts (large system prompt + tool schemas); 120s read-timed-out.
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

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
        model_name = model or self.default_model

        # Convert messages to Ollama/OpenAI chat format
        api_messages = self._format_messages(messages, system)

        payload: dict[str, Any] = {
            "model": model_name,
            "messages": api_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if tools:
            payload["tools"] = [self._format_tool(t) for t in tools]

        if stop_sequences:
            payload["options"]["stop"] = stop_sequences

        resp = await self._client.post("/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

        return self._parse_response(data, model_name)

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get("/api/tags")
            return resp.status_code == 200
        except Exception:
            return False

    # -- Format helpers ---------------------------------------------------

    def _format_messages(
        self, messages: list[LLMMessage], system: str
    ) -> list[dict[str, Any]]:
        api_msgs: list[dict[str, Any]] = []

        if system:
            api_msgs.append({"role": "system", "content": system})

        for msg in messages:
            if msg.role == Role.TOOL_RESULT:
                api_msgs.append({
                    "role": "tool",
                    "content": msg.content if isinstance(msg.content, str) else json.dumps(msg.content),
                })
            elif msg.role == Role.ASSISTANT and msg.tool_calls:
                api_msgs.append({
                    "role": "assistant",
                    "content": msg.content if isinstance(msg.content, str) else "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                # Ollama's NATIVE /api/chat requires arguments as a
                                # JSON object (only the OpenAI-compat endpoint takes
                                # a stringified form). A string here 400s every
                                # round that replays tool-call history.
                                "arguments": tc.arguments
                                if isinstance(tc.arguments, dict)
                                else json.loads(tc.arguments or "{}"),
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                })
            else:
                api_msgs.append({
                    "role": msg.role.value if isinstance(msg.role, Role) else msg.role,
                    "content": msg.content if isinstance(msg.content, str) else str(msg.content),
                })

        return api_msgs

    @staticmethod
    def _format_tool(t: ToolSchema) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }

    @staticmethod
    def _parse_response(data: dict[str, Any], model: str) -> LLMResponse:
        msg = data.get("message", {})
        content = msg.get("content", "")

        tool_calls: list[ToolCallRequest] = []
        for tc in msg.get("tool_calls", []) or []:
            fn = tc.get("function", {})
            args = fn.get("arguments", {}) or {}
            if isinstance(args, str):
                args = json.loads(args)
            tool_calls.append(ToolCallRequest(
                id=tc.get("id", uuid.uuid4().hex[:12]),
                name=fn.get("name", ""),
                arguments=args if isinstance(args, dict) else {},
            ))

        usage = TokenUsage(
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
        )

        stop_reason = "tool_use" if tool_calls else "end_turn"

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            stop_reason=stop_reason,
            model=model,
            raw=data,
        )

    async def close(self) -> None:
        await self._client.aclose()


# ============================================================================
# Anthropic
# ============================================================================

class AnthropicProvider(LLMProvider):
    """Wraps the official Anthropic SDK."""

    provider_name = "anthropic"

    def __init__(
        self,
        api_key: str,
        default_model: str = "claude-sonnet-4-20250514",
    ) -> None:
        import anthropic
        self.default_model = default_model
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

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
        model_name = model or self.default_model

        api_kwargs: dict[str, Any] = {
            "model": model_name,
            "max_tokens": max_tokens,
            "messages": self._format_messages(messages),
        }
        if system:
            api_kwargs["system"] = system
        if temperature is not None:
            api_kwargs["temperature"] = temperature
        if tools:
            api_kwargs["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ]
        if stop_sequences:
            api_kwargs["stop_sequences"] = stop_sequences

        response = await self._client.messages.create(**api_kwargs)
        return self._parse_response(response, model_name)

    async def health_check(self) -> bool:
        try:
            # Small ping — count tokens for a trivial message
            await self._client.messages.count_tokens(
                model=self.default_model,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False

    # -- Format helpers ---------------------------------------------------

    @staticmethod
    def _format_messages(messages: list[LLMMessage]) -> list[dict[str, Any]]:
        api_msgs: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == Role.SYSTEM:
                continue  # system is passed separately to Anthropic

            if msg.role == Role.TOOL_RESULT:
                api_msgs.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id or "",
                        "content": msg.content if isinstance(msg.content, str) else json.dumps(msg.content),
                    }],
                })
            elif msg.role == Role.ASSISTANT and msg.tool_calls:
                blocks: list[dict[str, Any]] = []
                if isinstance(msg.content, str) and msg.content:
                    blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                api_msgs.append({"role": "assistant", "content": blocks})
            else:
                api_msgs.append({
                    "role": msg.role.value if isinstance(msg.role, Role) else msg.role,
                    "content": msg.content if isinstance(msg.content, str) else str(msg.content),
                })

        return api_msgs

    @staticmethod
    def _parse_response(response: Any, model: str) -> LLMResponse:
        text_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCallRequest(
                    id=block.id,
                    name=block.name,
                    arguments=block.input or {},
                ))

        usage = TokenUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

        return LLMResponse(
            content="\n".join(text_parts),
            tool_calls=tool_calls,
            usage=usage,
            stop_reason=response.stop_reason,
            model=model,
            raw=response,
        )


# ============================================================================
# OpenAI-Compatible (vLLM, Together, Groq, LM Studio, etc.)
# ============================================================================

class OpenAICompatibleProvider(LLMProvider):
    """
    Any API that speaks the OpenAI chat completions format.
    Works with: vLLM, Together AI, Groq, LM Studio, LocalAI, etc.
    """

    provider_name = "openai_compatible"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        default_model: str = "gpt-4o-mini",
        timeout: float = 120.0,
    ) -> None:
        self.default_model = default_model
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
        )

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
        model_name = model or self.default_model

        api_messages = self._format_messages(messages, system)

        payload: dict[str, Any] = {
            "model": model_name,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
            payload["tool_choice"] = "auto"
            logger.debug(
                "OpenAI-compat request: model=%s, %d tools, %d messages",
                model_name, len(tools), len(api_messages),
            )

        if stop_sequences:
            payload["stop"] = stop_sequences

        resp = await self._client.post("/chat/completions", json=payload)
        if resp.status_code != 200:
            error_body = resp.text[:1000]
            logger.error(
                "OpenAI-compat %d from %s: %s",
                resp.status_code, self._client.base_url, error_body,
            )
            # Groq tool_use_failed: the model generated a tool call but
            # Groq's validation rejected it (e.g. "true" instead of true).
            # Recover by parsing the failed_generation field.
            if resp.status_code == 400 and "tool_use_failed" in error_body and tools:
                recovered = self._recover_failed_tool_call(error_body, model_name, tools)
                if recovered:
                    logger.info("Recovered tool call from Groq failed_generation")
                    return recovered
            resp.raise_for_status()
        data = resp.json()
        result = self._parse_response(data, model_name)
        if tools:
            logger.debug(
                "OpenAI-compat response: tool_calls=%d, stop_reason=%s, content_len=%d",
                len(result.tool_calls), result.stop_reason, len(result.content),
            )
        return result

    def _recover_failed_tool_call(
        self, error_body: str, model: str, tools: list[ToolSchema],
    ) -> LLMResponse | None:
        """
        Recover from Groq's tool_use_failed error.
        Groq includes a `failed_generation` field with the raw tool call
        like: <function=name>{"arg": "val"}</function>
        Parse it, coerce types to match the schema, and return as LLMResponse.
        """
        import re
        try:
            err_data = json.loads(error_body)
            raw = err_data.get("error", {}).get("failed_generation", "")
            if not raw:
                return None

            # Parse <function=tool_name>{...}</function>
            m = re.search(r'<function=(\w+)>\s*(\{.*?\})\s*</function>', raw, re.DOTALL)
            if not m:
                return None

            tool_name = m.group(1)
            try:
                args = json.loads(m.group(2))
            except json.JSONDecodeError:
                return None

            # Coerce types based on tool schema
            schema = next((t for t in tools if t.name == tool_name), None)
            if schema:
                props = schema.parameters.get("properties", {})
                for key, val in list(args.items()):
                    if key in props and isinstance(val, str):
                        expected = props[key].get("type")
                        if expected == "boolean":
                            args[key] = val.lower() in ("true", "1", "yes")
                        elif expected == "integer":
                            try:
                                args[key] = int(val)
                            except ValueError:
                                pass

            return LLMResponse(
                content="",
                tool_calls=[ToolCallRequest(
                    id=f"recovered_{tool_name}",
                    name=tool_name,
                    arguments=args,
                )],
                model=model,
                stop_reason="tool_calls",
                usage=TokenUsage(input_tokens=0, output_tokens=0),
            )
        except Exception:
            logger.debug("Failed to recover tool call from error body", exc_info=True)
            return None

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get("/models")
            return resp.status_code == 200
        except Exception:
            return False

    # -- Format helpers ---------------------------------------------------

    @staticmethod
    def _format_messages(
        messages: list[LLMMessage], system: str
    ) -> list[dict[str, Any]]:
        api_msgs: list[dict[str, Any]] = []

        if system:
            api_msgs.append({"role": "system", "content": system})

        for msg in messages:
            if msg.role == Role.SYSTEM:
                continue
            if msg.role == Role.TOOL_RESULT:
                api_msgs.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id or "",
                    "content": msg.content if isinstance(msg.content, str) else json.dumps(msg.content),
                })
            elif msg.role == Role.ASSISTANT and msg.tool_calls:
                api_msgs.append({
                    "role": "assistant",
                    "content": msg.content if isinstance(msg.content, str) else "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                })
            else:
                api_msgs.append({
                    "role": msg.role.value if isinstance(msg.role, Role) else msg.role,
                    "content": msg.content if isinstance(msg.content, str) else str(msg.content),
                })

        return api_msgs

    @staticmethod
    def _parse_response(data: dict[str, Any], model: str) -> LLMResponse:
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content", "") or ""

        tool_calls: list[ToolCallRequest] = []
        for tc in msg.get("tool_calls", []) or []:
            fn = tc.get("function", {})
            args = fn.get("arguments", "{}") or "{}"
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"raw": args}
            tool_calls.append(ToolCallRequest(
                id=tc.get("id", uuid.uuid4().hex[:12]),
                name=fn.get("name", ""),
                arguments=args if isinstance(args, dict) else {},
            ))

        usage_data = data.get("usage", {})
        usage = TokenUsage(
            input_tokens=usage_data.get("prompt_tokens", 0),
            output_tokens=usage_data.get("completion_tokens", 0),
        )

        finish = choice.get("finish_reason", "stop")
        stop_reason = "tool_use" if finish == "tool_calls" else "end_turn"

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            stop_reason=stop_reason,
            model=model,
            raw=data,
        )

    async def close(self) -> None:
        await self._client.aclose()


# ============================================================================
# Gemini (Google) — OpenAI-compatible endpoint
# ============================================================================

class GeminiProvider(OpenAICompatibleProvider):
    """
    Google Gemini via its OpenAI-compatible endpoint.
    Uses: https://generativelanguage.googleapis.com/v1beta/openai/

    This avoids needing the google-genai SDK — pure httpx.
    """

    provider_name = "gemini"

    _GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"

    def __init__(
        self,
        api_key: str,
        default_model: str = "gemini-2.5-flash",
        timeout: float = 120.0,
    ) -> None:
        self._api_key = api_key
        self.default_model = default_model
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=self._GEMINI_BASE,
            headers=headers,
            timeout=timeout,
        )

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get("/models")
            return resp.status_code == 200
        except Exception:
            return False


# ============================================================================
# Gemini (Google) — Native REST API (separate rate limit pool)
# ============================================================================

class GeminiNativeProvider(LLMProvider):
    """
    Google Gemini via its NATIVE REST API (not OpenAI-compatible).
    Uses: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent

    This has a SEPARATE rate limit pool from the OpenAI-compat endpoint,
    so it serves as a fallback when the compat endpoint is throttled.
    """

    provider_name = "gemini_native"

    _BASE = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(
        self,
        api_key: str,
        default_model: str = "gemini-2.0-flash",
        timeout: float = 120.0,
    ) -> None:
        self._api_key = api_key
        self.default_model = default_model
        self._client = httpx.AsyncClient(
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        system: str = "",
        tools: list[ToolSchema] | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> LLMResponse:
        model_name = model or self.default_model
        url = f"{self._BASE}/models/{model_name}:generateContent?key={self._api_key}"

        # Build native Gemini content format
        contents = []
        for msg in messages:
            if msg.role == Role.TOOL_RESULT:
                contents.append({
                    "role": "user",
                    "parts": [{
                        "functionResponse": {
                            "name": msg.tool_call_id or "tool",
                            "response": {"result": msg.content},
                        }
                    }],
                })
            elif msg.role == Role.ASSISTANT and msg.tool_calls:
                parts = []
                if msg.content:
                    parts.append({"text": msg.content})
                for tc in msg.tool_calls:
                    parts.append({
                        "functionCall": {
                            "name": tc.name,
                            "args": tc.arguments,
                        }
                    })
                contents.append({"role": "model", "parts": parts})
            else:
                role = "user" if msg.role == Role.USER else "model"
                contents.append({"role": role, "parts": [{"text": msg.content}]})

        body: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        # Add tool declarations (function calling support)
        if tools:
            body["tools"] = [{
                "functionDeclarations": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    }
                    for t in tools
                ],
            }]

        resp = await self._client.post(url, json=body)
        resp.raise_for_status()
        data = resp.json()

        # Parse native response (text + function calls)
        candidate = data.get("candidates", [{}])[0]
        text_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []

        for part in candidate.get("content", {}).get("parts", []):
            if "text" in part:
                text_parts.append(part["text"])
            elif "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append(ToolCallRequest(
                    id=uuid.uuid4().hex[:12],
                    name=fc.get("name", ""),
                    arguments=fc.get("args") or {},
                ))

        usage_data = data.get("usageMetadata", {})

        return LLMResponse(
            content="\n".join(text_parts),
            tool_calls=tool_calls,
            model=model_name,
            usage=TokenUsage(
                input_tokens=usage_data.get("promptTokenCount", 0),
                output_tokens=usage_data.get("candidatesTokenCount", 0),
            ),
            stop_reason="tool_use" if tool_calls else "end_turn",
        )

    async def health_check(self) -> bool:
        try:
            url = f"{self._BASE}/models?key={self._api_key}"
            resp = await self._client.get(url)
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()


# ============================================================================
# Gemini with automatic fallback
# ============================================================================

class GeminiWithFallback(LLMProvider):
    """
    Tries the OpenAI-compatible Gemini endpoint first.
    If it gets a 429, retries with exponential backoff, then falls back
    to the native Gemini REST endpoint (separate rate-limit pool).
    If both Gemini endpoints fail (e.g. daily quota exhausted),
    automatically falls back to OpenAI as a third-tier provider.

    Circuit breaker: after a 429, Gemini is skipped for _COOLDOWN_SECS
    so subsequent calls in the same agentic loop go straight to Groq.
    """

    provider_name = "gemini"

    def __init__(
        self,
        api_key: str,
        default_model: str = "gemini-2.0-flash",
        timeout: float = 120.0,
        *,
        openai_api_key: str = "",
        openai_model: str = "gpt-4o-mini",
        openai_base_url: str = "https://api.openai.com/v1",
    ):
        self._primary = GeminiProvider(api_key, default_model, timeout)
        self._fallback = GeminiNativeProvider(api_key, default_model, timeout)
        self.default_model = default_model
        self._gemini_cooldown_until: float = 0.0  # circuit breaker timestamp

        # Third-tier: OpenAI fallback when entire Gemini quota is exhausted
        self._openai: OpenAICompatibleProvider | None = None
        if openai_api_key:
            self._openai = OpenAICompatibleProvider(
                api_key=openai_api_key,
                base_url=openai_base_url,
                default_model=openai_model,
                timeout=timeout,
            )
            self._openai_model = openai_model
            logger.info("OpenAI fallback configured (model=%s)", openai_model)

    _RETRYABLE = ("429", "400", "401", "403", "404", "500", "503")
    _MAX_RETRIES = 1          # 1 retry max — save tokens for fallback
    _BACKOFF_BASE = 2         # seconds
    _COOLDOWN_SECS = 60       # skip Gemini for 60s after 429

    def _is_retryable(self, exc: Exception) -> bool:
        err = str(exc)
        return any(code in err for code in self._RETRYABLE)

    def _is_rate_limit(self, exc: Exception) -> bool:
        return "429" in str(exc)

    async def _call_with_retry(self, provider, label, messages, **kwargs):
        """Call a provider with retry + exponential backoff on 429."""
        import asyncio
        last_exc = None
        for attempt in range(1 + self._MAX_RETRIES):
            try:
                return await provider.generate(messages, **kwargs)
            except Exception as exc:
                last_exc = exc
                if not self._is_retryable(exc):
                    raise
                if attempt < self._MAX_RETRIES and self._is_rate_limit(exc):
                    delay = self._BACKOFF_BASE * (2 ** attempt)
                    logger.info(
                        "%s 429 rate-limited (attempt %d/%d) — retrying in %ds",
                        label, attempt + 1, 1 + self._MAX_RETRIES, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    break
        raise last_exc  # type: ignore[misc]

    async def generate(self, messages, *, system="", model=None, temperature=0.7, max_tokens=4096, **kwargs):
        import time as _time
        # Safety: ignore non-Gemini model names (e.g. from stale DB config)
        if model and not model.startswith("gemini"):
            logger.warning(
                "Ignoring non-Gemini model '%s' — using default '%s'",
                model, self.default_model,
            )
            model = None
        gen_kwargs = dict(system=system, model=model, temperature=temperature, max_tokens=max_tokens, **kwargs)

        # Circuit breaker: skip Gemini if recently rate-limited
        gemini_available = _time.monotonic() >= self._gemini_cooldown_until

        if gemini_available:
            # 1) Gemini OpenAI-compat endpoint (with retry)
            try:
                return await self._call_with_retry(
                    self._primary, "Gemini OpenAI-compat", messages, **gen_kwargs,
                )
            except Exception as exc:
                if not self._is_retryable(exc):
                    raise
                logger.info("Gemini OpenAI-compat exhausted (%s) — trying native REST", str(exc)[:80])

            # 2) Gemini native REST endpoint (with retry, separate rate-limit pool)
            try:
                return await self._call_with_retry(
                    self._fallback, "Gemini native", messages, **gen_kwargs,
                )
            except Exception as exc:
                if not self._is_retryable(exc):
                    raise
                logger.warning("Gemini native also exhausted (%s)", str(exc)[:80])
                # Activate circuit breaker — skip Gemini for next _COOLDOWN_SECS
                self._gemini_cooldown_until = _time.monotonic() + self._COOLDOWN_SECS
                logger.info("Gemini circuit breaker ON for %ds", self._COOLDOWN_SECS)
        else:
            logger.info("Gemini circuit breaker active — skipping straight to fallback")

        # 3) OpenAI fallback (if configured)
        if self._openai:
            logger.info("Falling back to OpenAI (%s)", self._openai_model)
            return await self._openai.generate(
                messages, system=system, model=self._openai_model,
                temperature=temperature, max_tokens=max_tokens, **kwargs,
            )

        raise RuntimeError(
            "All LLM providers are temporarily unavailable (rate-limited). "
            "Please wait a minute and try again, or set OPENAI_API_KEY in .env for automatic fallback."
        )

    async def health_check(self) -> bool:
        if await self._primary.health_check():
            return True
        if await self._fallback.health_check():
            return True
        if self._openai:
            return await self._openai.health_check()
        return False

    async def close(self) -> None:
        await self._primary.close()
        await self._fallback.close()
        if self._openai:
            await self._openai.close()


# ============================================================================
# Factory
# ============================================================================

def create_llm_provider(
    provider: str = "ollama",
    *,
    api_key: str = "",
    base_url: str = "",
    model: str = "",
    openai_api_key: str = "",
    openai_model: str = "gpt-4o-mini",
    openai_base_url: str = "https://api.openai.com/v1",
) -> LLMProvider:
    """
    Factory to create the right LLM provider from config.

    Args:
        provider:  "ollama" | "anthropic" | "openai_compatible" | "gemini"
        api_key:   API key (not needed for Ollama)
        base_url:  Override base URL
        model:     Default model name
        openai_api_key:  OpenAI API key for cross-provider fallback (Gemini→OpenAI)
        openai_model:    OpenAI model to use as fallback
        openai_base_url: OpenAI base URL
    """
    if provider == "ollama":
        return OllamaProvider(
            base_url=base_url or "http://localhost:11434",
            default_model=model or "llama3.1:8b",
        )
    elif provider == "anthropic":
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY required for Anthropic provider")
        return AnthropicProvider(
            api_key=api_key,
            default_model=model or "claude-sonnet-4-20250514",
        )
    elif provider == "openai_compatible":
        return OpenAICompatibleProvider(
            api_key=api_key,
            base_url=base_url or "https://api.openai.com/v1",
            default_model=model or "gpt-4o-mini",
        )
    elif provider == "gemini":
        if not api_key:
            raise ValueError("GEMINI_API_KEY required for Gemini provider")
        return GeminiWithFallback(
            api_key=api_key,
            default_model=model or "gemini-2.0-flash",
            openai_api_key=openai_api_key,
            openai_model=openai_model or "gpt-4o-mini",
            openai_base_url=openai_base_url or "https://api.openai.com/v1",
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
