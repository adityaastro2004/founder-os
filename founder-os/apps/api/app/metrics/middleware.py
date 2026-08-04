"""
HTTP request instrumentation (ADR-018).

The one thing this file exists to get right is **route labelling**. Labelling with
the raw request path would mint a new time series for every ``/agents/<uuid>`` ever
requested and blow the 10k-series free-tier budget within a day. Every request is
therefore attributed to its route *template*.

Starlette 1.3.1 does not put the matched route on the scope — it sets only
``scope["endpoint"]`` and ``scope["path_params"]`` (``starlette/routing.py:249``).
So we build an endpoint-function → path-template map once, lazily, on the first
request (by which point ``app.routes`` is fully populated), and look up O(1) after
the handler runs. Anything unmatched — 404s, malformed paths, probes — collapses
into a single ``__unmatched__`` series.

Like ``RateLimitMiddleware``, this fails open: an instrumentation bug must never
turn into an outage.
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from app.metrics.registry import (
    http_request_duration_seconds,
    http_requests_in_flight,
    http_requests_total,
)

UNMATCHED = "__unmatched__"


def _status_class(status_code: int) -> str:
    """Collapse a status code to its class: 200 -> "2xx"."""
    return f"{status_code // 100}xx"


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record request count, latency and in-flight gauge for every request."""

    def __init__(self, app) -> None:
        super().__init__(app)
        self._route_map: dict[object, str] | None = None

    def _build_route_map(self, request: Request) -> dict[object, str]:
        """Map each route's endpoint callable to its path template."""
        mapping: dict[object, str] = {}
        for route in request.app.routes:
            endpoint = getattr(route, "endpoint", None)
            path = getattr(route, "path", None)
            if endpoint is not None and isinstance(path, str):
                # setdefault: if one function is mounted at two paths, the first
                # wins rather than the label flapping between them.
                mapping.setdefault(endpoint, path)
            elif isinstance(route, Route) and isinstance(path, str):
                mapping.setdefault(route, path)
        return mapping

    def _route_label(self, request: Request) -> str:
        endpoint = request.scope.get("endpoint")
        if endpoint is None:
            return UNMATCHED
        if self._route_map is None:
            self._route_map = self._build_route_map(request)
        template = self._route_map.get(endpoint)
        if template is None:
            # A route registered after the map was built (dev reload, test app).
            self._route_map = self._build_route_map(request)
            template = self._route_map.get(endpoint)
        return template or UNMATCHED

    async def dispatch(self, request: Request, call_next):
        # The /metrics endpoint must not observe itself: every scrape would
        # otherwise bump its own counters, and the value is nil anyway.
        if request.url.path == "/metrics":
            return await call_next(request)

        start = time.perf_counter()
        try:
            http_requests_in_flight.inc()
        except Exception:
            pass

        status_code = 500
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            # An unhandled exception is a 5xx as far as the metrics are
            # concerned; re-raise so the framework still handles it normally.
            raise
        finally:
            # Timing stops when response headers are ready, NOT when the body
            # finishes streaming. Founder OS serves SSE endpoints that stay open
            # for minutes; measuring to body-completion would make their latency
            # a measure of how long the user kept the tab open.
            elapsed = time.perf_counter() - start
            try:
                route = self._route_label(request)
                http_requests_in_flight.dec()
                http_requests_total.labels(
                    route=route,
                    method=request.method,
                    status_class=_status_class(status_code),
                ).inc()
                http_request_duration_seconds.labels(route=route).observe(elapsed)
            except Exception:
                pass
