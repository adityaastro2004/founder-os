"""
Founder OS metrics — Prometheus exposition for Grafana Cloud (ADR-018).

Public surface for the rest of the app. Every recorder here is **fail-open**: an
instrumentation bug must never break a request, a task, or an agent run. That is
the same discipline ``RateLimitMiddleware`` follows, and it is why each function
swallows exceptions rather than propagating them.

This module deliberately imports only ``registry`` — never ``routes`` or
``middleware``. The Celery worker imports ``app.agents.llm``, which imports this
package; keeping FastAPI out of that path keeps the worker's import graph honest.
``main.py`` imports ``app.metrics.routes`` and ``app.metrics.middleware`` directly.

Usage:

    from app.metrics import record_llm_call, instrumented_generate
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable

from app.metrics.registry import (
    REGISTRY,
    approval_decisions_total,
    estimate_cost_usd,
    llm_cost_usd_total,
    llm_fallback_total,
    llm_request_duration_seconds,
    llm_requests_total,
    llm_tokens_total,
    orchestrator_runs_total,
)

logger = logging.getLogger(__name__)

__all__ = [
    "REGISTRY",
    "record_llm_call",
    "record_llm_fallback",
    "record_orchestrator_run",
    "record_approval_decision",
    "instrumented_generate",
]


def record_llm_call(
    *,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    duration_seconds: float,
    outcome: str,
) -> None:
    """Record one LLM ``generate()`` call: count, tokens, cost and latency."""
    try:
        model = model or "unknown"
        llm_requests_total.labels(provider=provider, model=model, outcome=outcome).inc()
        llm_request_duration_seconds.labels(provider=provider).observe(duration_seconds)
        if input_tokens:
            llm_tokens_total.labels(provider=provider, model=model, direction="input").inc(input_tokens)
        if output_tokens:
            llm_tokens_total.labels(provider=provider, model=model, direction="output").inc(output_tokens)
        cost = estimate_cost_usd(provider, model, input_tokens, output_tokens)
        if cost:
            llm_cost_usd_total.labels(provider=provider, model=model).inc(cost)
    except Exception:
        logger.debug("record_llm_call failed", exc_info=True)


def record_llm_fallback(from_provider: str, to_provider: str) -> None:
    """Record a provider tier transition (primary exhausted, next tier tried)."""
    try:
        llm_fallback_total.labels(from_provider=from_provider, to_provider=to_provider).inc()
    except Exception:
        logger.debug("record_llm_fallback failed", exc_info=True)


def record_orchestrator_run(outcome: str) -> None:
    """Record an orchestrator graph run reaching a terminal state."""
    try:
        orchestrator_runs_total.labels(outcome=outcome).inc()
    except Exception:
        logger.debug("record_orchestrator_run failed", exc_info=True)


def record_approval_decision(decision: str) -> None:
    """Record an approval-gate outcome."""
    try:
        approval_decisions_total.labels(decision=decision).inc()
    except Exception:
        logger.debug("record_approval_decision failed", exc_info=True)


def instrumented_generate(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorate an ``LLMProvider.generate`` implementation with metrics.

    Applied to the four **leaf** providers only. ``GeminiWithFallback`` delegates
    to decorated leaves, so decorating it as well would double-count every call;
    it records fallback transitions instead.

    The provider label comes from ``self.provider_name`` at call time, so
    ``GeminiProvider`` (which inherits ``OpenAICompatibleProvider.generate``) is
    still attributed to ``gemini``.
    """

    @functools.wraps(func)
    async def wrapper(self, *args: Any, **kwargs: Any):
        start = time.perf_counter()
        provider = getattr(self, "provider_name", "unknown")
        try:
            response = await func(self, *args, **kwargs)
        except Exception:
            record_llm_call(
                provider=provider,
                model=kwargs.get("model") or getattr(self, "default_model", "") or "unknown",
                input_tokens=0,
                output_tokens=0,
                duration_seconds=time.perf_counter() - start,
                outcome="error",
            )
            raise
        usage = getattr(response, "usage", None)
        record_llm_call(
            provider=provider,
            model=getattr(response, "model", "") or getattr(self, "default_model", "") or "unknown",
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            duration_seconds=time.perf_counter() - start,
            outcome="success",
        )
        return response

    return wrapper
