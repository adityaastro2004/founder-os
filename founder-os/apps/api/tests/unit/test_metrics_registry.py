"""Unit tests for the metrics registry, cost model and recorders (ADR-018).

The two invariants worth a test here are the ones that silently destroy the
system if violated: an unbounded/PII label (which both blows the 10k-series free
tier budget and ships user data to a third party), and a recorder that raises
into its caller.
"""

from __future__ import annotations

import pytest

from app.metrics import (
    instrumented_generate,
    record_approval_decision,
    record_llm_call,
    record_llm_fallback,
    record_orchestrator_run,
)
from app.metrics.registry import FORBIDDEN_LABELS, REGISTRY, estimate_cost_usd


def _all_label_names() -> set[str]:
    """Every label name declared by every collector in the app registry."""
    names: set[str] = set()
    for collector in list(REGISTRY._collector_to_names):  # noqa: SLF001 — no public API
        for label in getattr(collector, "_labelnames", ()) or ():
            names.add(label)
    return names


class TestLabelPolicy:
    def test_no_forbidden_labels_anywhere(self):
        """No metric may carry a user-identifying or unbounded label.

        Metrics leave the box to Grafana Cloud, so this is a PII control as much
        as a cardinality one. Per-user analysis belongs in PostHog.
        """
        offenders = _all_label_names() & FORBIDDEN_LABELS
        assert offenders == set(), f"forbidden metric labels declared: {sorted(offenders)}"

    def test_http_metrics_use_route_not_path(self):
        """`path` (raw, unbounded) must never be a label; `route` (template) is."""
        names = _all_label_names()
        assert "path" not in names
        assert "route" in names

    def test_latency_histogram_is_labelled_by_route_only(self):
        """Adding method/status here would multiply 12 buckets across ~100 routes."""
        from app.metrics.registry import http_request_duration_seconds

        assert http_request_duration_seconds._labelnames == ("route",)  # noqa: SLF001


class TestCostEstimation:
    def test_known_model_is_priced(self):
        # 1M input + 1M output on Sonnet 4 = $3 + $15
        cost = estimate_cost_usd("anthropic", "claude-sonnet-4-20250514", 1_000_000, 1_000_000)
        assert cost == pytest.approx(18.0)

    def test_dated_variant_matches_base_prefix(self):
        dated = estimate_cost_usd("anthropic", "claude-sonnet-4-20250514", 1000, 0)
        base = estimate_cost_usd("anthropic", "claude-sonnet-4", 1000, 0)
        assert dated == base > 0

    def test_longest_prefix_wins(self):
        """`claude-3-5-haiku` must not accidentally resolve to a shorter entry."""
        assert estimate_cost_usd("anthropic", "claude-haiku-4-5", 1_000_000, 0) == pytest.approx(0.80)

    def test_unknown_model_costs_zero_not_an_error(self):
        """A missing price entry under-reports spend; it never invents a number."""
        assert estimate_cost_usd("anthropic", "claude-model-from-2027", 1_000_000, 1_000_000) == 0.0

    def test_unknown_provider_costs_zero(self):
        assert estimate_cost_usd("some_new_provider", "gpt-4o", 1000, 1000) == 0.0

    def test_ollama_is_free(self):
        """Local inference is deliberately absent from the price table."""
        assert estimate_cost_usd("ollama", "llama3.1:8b", 1_000_000, 1_000_000) == 0.0


class TestRecordersFailOpen:
    """An instrumentation bug must never break a request or an agent run."""

    def test_record_llm_call_swallows_bad_input(self):
        record_llm_call(
            provider="anthropic",
            model=None,  # type: ignore[arg-type]
            input_tokens="not a number",  # type: ignore[arg-type]
            output_tokens=0,
            duration_seconds=0.1,
            outcome="success",
        )

    def test_other_recorders_swallow_bad_input(self):
        record_llm_fallback(None, None)  # type: ignore[arg-type]
        record_orchestrator_run(None)  # type: ignore[arg-type]
        record_approval_decision(None)  # type: ignore[arg-type]


class _FakeUsage:
    input_tokens = 10
    output_tokens = 5


class _FakeResponse:
    usage = _FakeUsage()
    model = "claude-sonnet-4"


class _FakeProvider:
    provider_name = "anthropic"
    default_model = "claude-sonnet-4"

    @instrumented_generate
    async def generate(self, messages, **kwargs):
        return _FakeResponse()


class _ExplodingProvider:
    provider_name = "anthropic"
    default_model = "claude-sonnet-4"

    @instrumented_generate
    async def generate(self, messages, **kwargs):
        raise RuntimeError("provider exploded")


def _counter_value(metric: str, **labels) -> float:
    value = REGISTRY.get_sample_value(metric, labels)
    return value or 0.0


class TestInstrumentedGenerate:
    async def test_records_tokens_and_returns_response(self):
        before = _counter_value(
            "fos_llm_tokens_total", provider="anthropic", model="claude-sonnet-4", direction="input"
        )
        response = await _FakeProvider().generate([])
        after = _counter_value(
            "fos_llm_tokens_total", provider="anthropic", model="claude-sonnet-4", direction="input"
        )

        assert isinstance(response, _FakeResponse)
        assert after - before == 10

    async def test_failure_is_counted_and_reraised(self):
        before = _counter_value(
            "fos_llm_requests_total", provider="anthropic", model="claude-sonnet-4", outcome="error"
        )
        with pytest.raises(RuntimeError, match="provider exploded"):
            await _ExplodingProvider().generate([])
        after = _counter_value(
            "fos_llm_requests_total", provider="anthropic", model="claude-sonnet-4", outcome="error"
        )

        assert after - before == 1

    async def test_preserves_wrapped_function_identity(self):
        """functools.wraps keeps the method introspectable (docs, debuggers)."""
        assert _FakeProvider.generate.__name__ == "generate"
