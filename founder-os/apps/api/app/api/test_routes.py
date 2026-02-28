"""
Founder OS — Test Routes (development only)
=============================================
Simple endpoints for testing the LLM + agent pipeline
without requiring Clerk authentication.

These routes are only registered when APP_ENV == "development".
"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents.llm import LLMMessage, Role, create_llm_provider
from app.config import get_settings

router = APIRouter(prefix="/api/test", tags=["test"])


# ── Request / Response ────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    system_prompt: str = Field(
        "You are a helpful AI startup advisor. Keep answers concise.",
        max_length=5000,
    )
    model: str | None = None
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(2048, ge=1, le=8192)


class ChatResponse(BaseModel):
    reply: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    duration_seconds: float


class ProviderInfoResponse(BaseModel):
    provider: str
    model: str
    healthy: bool


# ── Routes ────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def test_chat(body: ChatRequest):
    """
    Send a message to the configured LLM and get a response.
    No auth required — for development testing only.
    """
    settings = get_settings()

    # Build provider from current config
    provider = _create_provider(settings)

    messages = [LLMMessage(role=Role.USER, content=body.message)]

    start = time.time()
    try:
        response = await provider.generate(
            messages,
            system=body.system_prompt,
            model=body.model,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM call failed: {exc}")
    finally:
        if hasattr(provider, "close"):
            await provider.close()

    duration = time.time() - start

    return ChatResponse(
        reply=response.content,
        model=response.model or body.model or settings.GEMINI_MODEL,
        provider=provider.provider_name,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        duration_seconds=round(duration, 3),
    )


@router.get("/provider", response_model=ProviderInfoResponse)
async def test_provider_info():
    """Check which LLM provider is configured and whether it's healthy."""
    settings = get_settings()
    provider = _create_provider(settings)

    try:
        healthy = await provider.health_check()
    except Exception:
        healthy = False
    finally:
        if hasattr(provider, "close"):
            await provider.close()

    model = _get_model(settings)
    return ProviderInfoResponse(
        provider=settings.LLM_PROVIDER,
        model=model,
        healthy=healthy,
    )


# ── Helpers ───────────────────────────────────────────────────

def _create_provider(settings):
    """Build an LLM provider instance from the current settings."""
    return create_llm_provider(
        provider=settings.LLM_PROVIDER,
        api_key=_get_api_key(settings),
        base_url=_get_base_url(settings),
        model=_get_model(settings),
    )


def _get_api_key(settings) -> str:
    mapping = {
        "anthropic": settings.ANTHROPIC_API_KEY,
        "openai_compatible": settings.OPENAI_API_KEY,
        "gemini": settings.GEMINI_API_KEY,
    }
    return mapping.get(settings.LLM_PROVIDER, "")


def _get_base_url(settings) -> str:
    mapping = {
        "ollama": settings.OLLAMA_BASE_URL,
        "openai_compatible": settings.OPENAI_BASE_URL,
    }
    return mapping.get(settings.LLM_PROVIDER, "")


def _get_model(settings) -> str:
    mapping = {
        "ollama": settings.OLLAMA_MODEL,
        "anthropic": settings.ANTHROPIC_MODEL,
        "openai_compatible": settings.OPENAI_MODEL,
        "gemini": settings.GEMINI_MODEL,
    }
    return mapping.get(settings.LLM_PROVIDER, "")
