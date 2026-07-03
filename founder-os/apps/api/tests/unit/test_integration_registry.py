"""Adapter framework contract (ADR-010): registration, lookup, capability defaults."""
from datetime import datetime, timezone

import pytest

from app.integrations import registry
from app.integrations.base import (
    Capability,
    HealthStatus,
    IntegrationAdapter,
    ObservedEvent,
    SyncResult,
)


class FakeAdapter(IntegrationAdapter):
    name = "fake_tool"
    capabilities = Capability.OBSERVE | Capability.HEALTH

    async def configure(self, settings):
        self.settings = settings

    async def health(self):
        return HealthStatus(ok=True, detail="fake ok")

    async def observe(self, user_id):
        return [ObservedEvent(
            source=self.name, kind="thing.seen", external_id="x1",
            payload={"user": user_id}, observed_at=datetime.now(timezone.utc),
        )]


@pytest.fixture(autouse=True)
def clean_registry():
    registry._reset_for_tests()
    yield
    registry._reset_for_tests()


def test_register_and_get():
    a = FakeAdapter()
    registry.register(a)
    assert registry.get("fake_tool") is a
    assert registry.all_adapters() == {"fake_tool": a}


def test_register_rejects_duplicates_and_unnamed():
    registry.register(FakeAdapter())
    with pytest.raises(ValueError):
        registry.register(FakeAdapter())          # duplicate name

    class Unnamed(FakeAdapter):
        name = ""

    with pytest.raises(ValueError):
        registry.register(Unnamed())

    with pytest.raises(KeyError):
        registry.get("nope")


async def test_observe_returns_provenance_tagged_events():
    a = FakeAdapter()
    events = await a.observe("user-1")
    assert events[0].provenance == "observed"
    assert events[0].source == "fake_tool"


async def test_unsupported_capabilities_raise():
    a = FakeAdapter()
    with pytest.raises(NotImplementedError):
        await a.sync("user-1", [{"anything": 1}])


def test_sync_result_defaults():
    r = SyncResult(ok=True)
    assert r.pushed == 0
    assert r.errors == []
