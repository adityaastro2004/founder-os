"""
The ``GET /metrics`` scrape endpoint (ADR-018).

This endpoint is *not* public. It discloses internal route names, traffic volumes
and LLM spend, so three things guard it, in depth:

  1. It is absent from ``Caddyfile`` — nothing outside the compose network can
     route to it at all. Alloy scrapes ``api:8000`` directly.
  2. It requires a ``METRICS_TOKEN`` bearer token, compared in constant time.
  3. It is only mounted when explicitly enabled, and outside development an empty
     token disables it rather than leaving it open. Fail closed.

Disabled means *not mounted* — a 404, not a 401. An unmounted route reveals
nothing about whether metrics exist.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, HTTPException, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.config import Settings, get_settings
from app.metrics.celery_bridge import snapshot_celery_metrics
from app.metrics.registry import REGISTRY

router = APIRouter(tags=["metrics"])


def metrics_endpoint_enabled(settings: Settings) -> bool:
    """Whether ``/metrics`` should be mounted at all.

    An empty ``METRICS_TOKEN`` is tolerated only in development, where the port is
    not reachable from anywhere else anyway. In every other environment a missing
    token disables the endpoint — an unauthenticated metrics endpoint in
    production would be an information-disclosure hole, so the safe failure is
    "no metrics", not "open metrics".
    """
    if not settings.METRICS_ENABLED:
        return False
    if settings.METRICS_TOKEN:
        return True
    return settings.APP_ENV == "development"


def _authorized(request: Request, settings: Settings) -> bool:
    expected = settings.METRICS_TOKEN
    if not expected:
        # Only reachable in development (see metrics_endpoint_enabled).
        return True
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False
    # Constant-time: a plain == leaks the token one byte at a time under timing
    # analysis.
    return hmac.compare_digest(token, expected)


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    settings = get_settings()
    if not _authorized(request, settings):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Pull the worker's counters out of Redis before rendering. collect() is
    # synchronous and cannot await, so the snapshot has to happen here.
    try:
        from app.redis import get_redis

        await snapshot_celery_metrics(get_redis())
    except RuntimeError:
        # Redis not initialised (unit tests, degraded boot) — serve the rest.
        pass

    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
