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
        timeout: float = 120.0,
    ) -> None:
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
            args = fn.get("arguments", {})
            if isinstance(args, str):
                args = json.loads(args)
            tool_calls.append(ToolCallRequest(
                id=tc.get("id", uuid.uuid4().hex[:12]),
                name=fn.get("name", ""),
                arguments=args,
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
                    arguments=block.input,
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

        if stop_sequences:
            payload["stop"] = stop_sequences

        resp = await self._client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return self._parse_response(data, model_name)

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
            args = fn.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"raw": args}
            tool_calls.append(ToolCallRequest(
                id=tc.get("id", uuid.uuid4().hex[:12]),
                name=fn.get("name", ""),
                arguments=args,
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
# Gemini (Google)
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
# Factory
# ============================================================================

def create_llm_provider(
    provider: str = "ollama",
    *,
    api_key: str = "",
    base_url: str = "",
    model: str = "",
) -> LLMProvider:
    """
    Factory to create the right LLM provider from config.

    Args:
        provider:  "ollama" | "anthropic" | "openai_compatible" | "gemini"
        api_key:   API key (not needed for Ollama)
        base_url:  Override base URL
        model:     Default model name
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
        return GeminiProvider(
            api_key=api_key,
            default_model=model or "gemini-2.5-flash",
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
