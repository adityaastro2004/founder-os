"""
Metric definitions and the single application ``CollectorRegistry`` (ADR-018).

Importing this module has no side effects beyond constructing the metric objects —
it is safe to import from the API process, the Celery worker, or a test.

Cardinality is a hard budget, not a style preference: Grafana Cloud's free tier
caps us at 10k active series and silently drops data past it. Two rules follow,
and both are enforced by ``tests/unit/test_metrics_registry.py``:

  1. Never label with an unbounded value. HTTP metrics carry the *route template*
     (``/agents/{agent_id}``), never the raw path.
  2. Never label with anything user-identifying. Metrics leave the box to a third
     party, so this is a PII control at least as strict as ``app/log_sanitize.py``.
     Per-user analysis belongs in PostHog.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

# One registry, explicitly constructed. We do NOT use prometheus_client's global
# REGISTRY: it auto-registers process/GC collectors and makes test isolation
# painful, and a stray third-party import could inject series into our budget.
REGISTRY = CollectorRegistry()

# Label names that must never appear on any metric. Checked by a unit test rather
# than at runtime, so the cost is zero in production.
FORBIDDEN_LABELS = frozenset(
    {
        "user",
        "user_id",
        "userid",
        "email",
        "clerk_user_id",
        "org",
        "org_id",
        "tenant",
        "session_id",
        "ip",
        "path",  # the raw path — use `route` (the template) instead
        "url",
        "query",
        "prompt",
        "title",
    }
)


# ── HTTP ────────────────────────────────────────────────────────────────────
# `status_class` ("2xx"/"4xx"/"5xx") rather than the exact code: a 3-value label
# answers every question a dashboard asks at a fraction of the series count.
http_requests_total = Counter(
    "fos_http_requests_total",
    "HTTP requests handled, by route template, method and status class.",
    ["route", "method", "status_class"],
    registry=REGISTRY,
)

# Labelled by `route` ONLY. Adding method+status here would multiply an already
# 12-bucket metric across ~100 routes and eat the whole series budget.
http_request_duration_seconds = Histogram(
    "fos_http_request_duration_seconds",
    "HTTP request latency in seconds, by route template.",
    ["route"],
    registry=REGISTRY,
    # Tuned for an LLM-backed API: sub-second for CRUD, tens of seconds for agent
    # calls. The default buckets top out at 10s and would collapse every agent
    # request into +Inf.
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)

http_requests_in_flight = Gauge(
    "fos_http_requests_in_flight",
    "HTTP requests currently being handled.",
    registry=REGISTRY,
)


# ── LLM providers ───────────────────────────────────────────────────────────
llm_requests_total = Counter(
    "fos_llm_requests_total",
    "LLM generate() calls, by provider, model and outcome (success|error).",
    ["provider", "model", "outcome"],
    registry=REGISTRY,
)

llm_tokens_total = Counter(
    "fos_llm_tokens_total",
    "LLM tokens consumed, by provider, model and direction (input|output).",
    ["provider", "model", "direction"],
    registry=REGISTRY,
)

llm_cost_usd_total = Counter(
    "fos_llm_cost_usd_total",
    "Estimated LLM spend in USD, by provider and model.",
    ["provider", "model"],
    registry=REGISTRY,
)

llm_request_duration_seconds = Histogram(
    "fos_llm_request_duration_seconds",
    "LLM generate() latency in seconds, by provider.",
    ["provider"],
    registry=REGISTRY,
    buckets=(0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0, 300.0),
)

llm_fallback_total = Counter(
    "fos_llm_fallback_total",
    "Provider fallback transitions (tier N exhausted, tier N+1 attempted).",
    ["from_provider", "to_provider"],
    registry=REGISTRY,
)


# ── Agents / orchestrator ───────────────────────────────────────────────────
orchestrator_runs_total = Counter(
    "fos_orchestrator_runs_total",
    "Orchestrator graph runs that reached a terminal state, by outcome.",
    ["outcome"],
    registry=REGISTRY,
)

approval_decisions_total = Counter(
    "fos_approval_decisions_total",
    "Approval-gate decisions, by decision (auto_approved|requires_approval|blocked).",
    ["decision"],
    registry=REGISTRY,
)


# ── Business aggregates (refreshed by app/metrics/business.py) ──────────────
users_total = Gauge(
    "fos_users_total",
    "Registered, non-deleted users.",
    registry=REGISTRY,
)

users_active_7d = Gauge(
    "fos_users_active_7d",
    "Users who logged in within the last 7 days.",
    registry=REGISTRY,
)

tasks_by_status = Gauge(
    "fos_tasks_by_status",
    "Tasks grouped by status.",
    ["status"],
    registry=REGISTRY,
)

state_entities = Gauge(
    "fos_state_entities",
    "Active Company State Engine entities, by entity type.",
    ["entity_type"],
    registry=REGISTRY,
)

integration_sync_age_seconds = Gauge(
    "fos_integration_sync_age_seconds",
    "Seconds since the most recent successful sync, by integration type. "
    "A climbing value means an adapter has stalled.",
    ["integration_type"],
    registry=REGISTRY,
)

business_refresh_failures_total = Counter(
    "fos_business_refresh_failures_total",
    "Failed runs of the periodic business-metrics refresh job.",
    registry=REGISTRY,
)


# ── LLM pricing ─────────────────────────────────────────────────────────────
# USD per 1M tokens, (input, output), keyed by (provider, model-prefix).
#
# MAINTENANCE: this table goes stale whenever a provider reprices. It is
# deliberately the ONLY place cost is encoded. An unknown model still records
# tokens and latency — it just contributes 0 to the cost counter, so a missing
# entry under-reports spend rather than inventing a number.
_PRICE_PER_MTOK: dict[tuple[str, str], tuple[float, float]] = {
    ("anthropic", "claude-opus-4"): (15.00, 75.00),
    ("anthropic", "claude-sonnet-4"): (3.00, 15.00),
    ("anthropic", "claude-haiku-4"): (0.80, 4.00),
    ("anthropic", "claude-3-5-haiku"): (0.80, 4.00),
    ("gemini", "gemini-2.0-flash"): (0.10, 0.40),
    ("gemini", "gemini-1.5-flash"): (0.075, 0.30),
    ("gemini", "gemini-1.5-pro"): (1.25, 5.00),
    ("openai_compatible", "llama-3.3-70b"): (0.59, 0.79),  # Groq
    ("openai_compatible", "gpt-4o-mini"): (0.15, 0.60),
    ("openai_compatible", "gpt-4o"): (2.50, 10.00),
    # Ollama runs locally — electricity is not billed here, so it stays $0 by
    # omission rather than by a 0.0 entry that would look like a stale price.
}


def estimate_cost_usd(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD spend for one call. Returns 0.0 for unpriced models.

    Matching is longest-prefix on the model name so that dated variants
    (``claude-sonnet-4-20250514``) resolve to their base price entry.
    """
    best: tuple[float, float] | None = None
    best_len = -1
    for (prov, prefix), price in _PRICE_PER_MTOK.items():
        if prov == provider and model.startswith(prefix) and len(prefix) > best_len:
            best, best_len = price, len(prefix)
    if best is None:
        return 0.0
    in_rate, out_rate = best
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000
