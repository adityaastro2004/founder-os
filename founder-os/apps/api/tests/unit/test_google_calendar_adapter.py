"""GoogleCalendarAdapter: thin facade, no business logic, fake transport only."""
from unittest.mock import AsyncMock, patch

from app.integrations.base import Capability
from app.integrations.google_calendar.adapter import GoogleCalendarAdapter


def test_identity_and_capabilities():
    a = GoogleCalendarAdapter()
    assert a.name == "google_calendar"
    assert Capability.OBSERVE in a.capabilities
    assert Capability.HEALTH in a.capabilities


async def test_health_reflects_config(monkeypatch):
    a = GoogleCalendarAdapter()
    monkeypatch.setattr(a, "_client_configured", lambda: False)
    status = await a.health()
    assert status.ok is False

    monkeypatch.setattr(a, "_client_configured", lambda: True)
    status = await a.health()
    assert status.ok is True


async def test_observe_wraps_upcoming_events():
    a = GoogleCalendarAdapter()
    fake_events = [{
        "id": "evt_1",
        "summary": "Standup",
        "start": {"dateTime": "2026-07-06T09:00:00Z"},
    }]
    with patch(
        "app.integrations.google_calendar.adapter.client.list_upcoming_events",
        new=AsyncMock(return_value=fake_events),
    ):
        events = await a.observe("user-1")

    assert len(events) == 1
    assert events[0].source == "google_calendar"
    assert events[0].external_id == "evt_1"
    assert events[0].provenance == "observed"
    assert events[0].payload["summary"] == "Standup"
