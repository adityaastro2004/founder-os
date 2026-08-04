"""Unit tests for the /metrics endpoint, middleware and Celery bridge (ADR-018).

Covers the three things that would be expensive to discover in production:
route-template labelling (cardinality), the token guard (information
disclosure), and the Celery collector tolerating a worker that never started.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.metrics import routes as metrics_routes
from app.metrics.celery_bridge import (
    KEY_DURATION_COUNT,
    KEY_DURATION_SUM,
    KEY_TASKS,
    CeleryCollector,
    reset_snapshot,
    snapshot_celery_metrics,
)
from app.metrics.middleware import UNMATCHED, MetricsMiddleware
from app.metrics.registry import REGISTRY


class _StubSettings:
    """Stands in for Settings — only the fields the endpoint reads."""

    def __init__(self, *, enabled=True, token="", env="production"):
        self.METRICS_ENABLED = enabled
        self.METRICS_TOKEN = token
        self.APP_ENV = env


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/agents/{agent_id}")
    async def get_agent(agent_id: str):
        return {"id": agent_id}

    @app.get("/boom")
    async def boom():
        raise RuntimeError("kaboom")

    app.add_middleware(MetricsMiddleware)
    return app


def _series_for(metric: str) -> dict[tuple, float]:
    """All samples of `metric` keyed by their label-value tuple."""
    found = {}
    for family in REGISTRY.collect():
        for sample in family.samples:
            if sample.name == metric:
                found[tuple(sorted(sample.labels.items()))] = sample.value
    return found


class TestRouteTemplateLabelling:
    def test_distinct_ids_collapse_to_one_series(self):
        """The whole cardinality budget rests on this."""
        client = TestClient(_build_app())
        for agent_id in ("123", "456", "789", "a-uuid-shaped-thing"):
            assert client.get(f"/agents/{agent_id}").status_code == 200

        routes = {
            dict(labels).get("route")
            for labels in _series_for("fos_http_requests_total")
        }

        assert "/agents/{agent_id}" in routes
        # Four distinct ids, one series — that is the entire point.
        assert len([r for r in routes if r.startswith("/agents")]) == 1
        for raw in ("/agents/123", "/agents/456", "/agents/789"):
            assert raw not in routes, f"raw path {raw} leaked into a metric label"

    def test_unmatched_paths_share_one_series(self):
        client = TestClient(_build_app())
        client.get("/no-such-route-1")
        client.get("/no-such-route-2")

        routes = {
            dict(labels).get("route") for labels in _series_for("fos_http_requests_total")
        }
        assert UNMATCHED in routes
        assert "/no-such-route-1" not in routes


class TestMiddlewareBehaviour:
    def test_response_is_unchanged(self):
        client = TestClient(_build_app())
        response = client.get("/agents/42")
        assert response.status_code == 200
        assert response.json() == {"id": "42"}

    def test_handler_exception_still_propagates(self):
        client = TestClient(_build_app(), raise_server_exceptions=False)
        assert client.get("/boom").status_code == 500

    def test_in_flight_returns_to_zero(self):
        client = TestClient(_build_app())
        client.get("/agents/1")
        assert REGISTRY.get_sample_value("fos_http_requests_in_flight") == 0.0


class TestEndpointGuard:
    def test_enabled_matrix(self):
        # Disabled outright.
        assert not metrics_routes.metrics_endpoint_enabled(_StubSettings(enabled=False, token="t"))
        # Token present -> mounted in any environment.
        assert metrics_routes.metrics_endpoint_enabled(_StubSettings(token="t", env="production"))
        # No token in production -> NOT mounted. Fail closed: an unauthenticated
        # metrics endpoint in prod would be an information-disclosure hole.
        assert not metrics_routes.metrics_endpoint_enabled(_StubSettings(token="", env="production"))
        # No token in development -> mounted for convenience.
        assert metrics_routes.metrics_endpoint_enabled(_StubSettings(token="", env="development"))

    @pytest.fixture
    def client(self, monkeypatch):
        monkeypatch.setattr(
            metrics_routes, "get_settings", lambda: _StubSettings(token="secret-token")
        )
        app = FastAPI()
        app.include_router(metrics_routes.router)
        return TestClient(app)

    def test_401_without_token(self, client):
        response = client.get("/metrics")
        assert response.status_code == 401
        assert response.headers.get("www-authenticate") == "Bearer"

    def test_401_with_wrong_token(self, client):
        response = client.get("/metrics", headers={"Authorization": "Bearer wrong"})
        assert response.status_code == 401

    def test_401_with_wrong_scheme(self, client):
        response = client.get("/metrics", headers={"Authorization": "Basic secret-token"})
        assert response.status_code == 401

    def test_200_with_correct_token(self, client):
        response = client.get("/metrics", headers={"Authorization": "Bearer secret-token"})
        assert response.status_code == 200
        assert "fos_http_requests" in response.text

    def test_404_when_not_mounted(self, monkeypatch):
        """Disabled means absent, not 401 — a 401 would confirm metrics exist."""
        settings = _StubSettings(enabled=False, token="secret-token")
        app = FastAPI()
        if metrics_routes.metrics_endpoint_enabled(settings):
            app.include_router(metrics_routes.router)
        assert TestClient(app).get("/metrics").status_code == 404


class _FakeRedis:
    def __init__(self, hashes=None, llens=None, explode=False):
        self._hashes = hashes or {}
        self._llens = llens or {}
        self._explode = explode

    async def hgetall(self, key):
        if self._explode:
            raise ConnectionError("redis is down")
        return self._hashes.get(key, {})

    async def llen(self, key):
        if self._explode:
            raise ConnectionError("redis is down")
        return self._llens.get(key, 0)


class TestCeleryBridge:
    def setup_method(self):
        reset_snapshot()

    def teardown_method(self):
        reset_snapshot()

    async def test_empty_snapshot_still_collects(self):
        """The worker may never have started — normal in dev and in CI."""
        families = list(CeleryCollector().collect())
        assert {f.name for f in families} == {
            "fos_celery_tasks",
            "fos_celery_task_duration_seconds",
            "fos_celery_queue_depth",
        }
        # Declared but empty: the families exist so dashboards resolve, with no
        # samples to imply activity that never happened.
        assert [s for f in families for s in f.samples] == []

    async def test_parses_worker_counters(self):
        redis = _FakeRedis(
            hashes={
                KEY_TASKS: {"app.tasks.agent_tasks.run_agent_task|agents|success": "7"},
                KEY_DURATION_SUM: {"app.tasks.agent_tasks.run_agent_task": "14.0"},
                KEY_DURATION_COUNT: {"app.tasks.agent_tasks.run_agent_task": "7"},
            },
            llens={"default": 0, "agents": 3, "orchestrator": 0},
        )
        await snapshot_celery_metrics(redis)

        samples = {
            (s.name, tuple(sorted(s.labels.items()))): s.value
            for family in CeleryCollector().collect()
            for s in family.samples
        }

        assert samples[
            (
                "fos_celery_tasks_total",
                (("queue", "agents"), ("state", "success"), ("task", "app.tasks.agent_tasks.run_agent_task")),
            )
        ] == 7.0
        assert samples[("fos_celery_queue_depth", (("queue", "agents"),))] == 3.0
        assert samples[
            ("fos_celery_task_duration_seconds_sum", (("task", "app.tasks.agent_tasks.run_agent_task"),))
        ] == 14.0

    async def test_malformed_field_is_skipped_not_fatal(self):
        redis = _FakeRedis(hashes={KEY_TASKS: {"missing-separators": "3", "a|b|c": "1"}})
        await snapshot_celery_metrics(redis)

        samples = [
            s
            for family in CeleryCollector().collect()
            for s in family.samples
            if s.name == "fos_celery_tasks_total"
        ]
        assert len(samples) == 1
        assert samples[0].labels == {"task": "a", "queue": "b", "state": "c"}

    async def test_redis_failure_keeps_previous_snapshot(self):
        """A scrape that 500s during an incident is worse than slightly stale data."""
        good = _FakeRedis(hashes={KEY_TASKS: {"t|default|success": "5"}}, llens={"default": 1})
        await snapshot_celery_metrics(good)
        await snapshot_celery_metrics(_FakeRedis(explode=True))

        values = [
            s.value
            for family in CeleryCollector().collect()
            for s in family.samples
            if s.name == "fos_celery_tasks_total"
        ]
        assert values == [5.0]
