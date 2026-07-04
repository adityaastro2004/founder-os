"""Adapter facade over the Google Calendar client (ADR-010).

Existing callers (mcp_tools, planner_routes, scheduler) keep calling client
functions directly — unchanged behavior. The adapter is the uniform seam the
State Engine (Phase 1) consumes; per-user OAuth tokens stay in the client's
token store.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.integrations import registry
from app.integrations.base import (
    Capability,
    HealthStatus,
    IntegrationAdapter,
    ObservedEvent,
)
from app.integrations.google_calendar import client


class GoogleCalendarAdapter(IntegrationAdapter):
    name = "google_calendar"
    capabilities = Capability.OBSERVE | Capability.HEALTH

    async def configure(self, settings: dict[str, Any]) -> None:
        # OAuth client creds come from env via get_settings(); nothing to store.
        return None

    def _client_configured(self) -> bool:
        s = get_settings()
        return bool(s.GOOGLE_CLIENT_ID and s.GOOGLE_CLIENT_SECRET)

    async def health(self) -> HealthStatus:
        if not self._client_configured():
            return HealthStatus(ok=False, detail="GOOGLE_CLIENT_ID/SECRET not configured")
        return HealthStatus(ok=True, detail="oauth client configured")

    async def observe(self, user_id: str) -> list[ObservedEvent]:
        s = get_settings()
        raw = await client.list_upcoming_events(
            user_id,
            s.GOOGLE_CLIENT_ID,
            s.GOOGLE_CLIENT_SECRET,
            max_results=50,
        )
        now = datetime.now(timezone.utc)
        return [
            ObservedEvent(
                source=self.name,
                kind="event.upcoming",
                external_id=str(e.get("id", "")),
                payload=e,
                observed_at=now,
            )
            for e in raw
        ]


def register_adapter() -> None:
    # Idempotent: lifespan can run more than once per process (e.g. multiple
    # TestClient contexts); a second registration must not kill startup (S2).
    if "google_calendar" in registry.all_adapters():
        return
    registry.register(GoogleCalendarAdapter())
