"""Unit tests for graph context snapshot/hydrate helpers (Task 2)."""

import json

import pytest

from app.agents.graph.context import snapshot_context, hydrate_volatile


class _FakeMemory:
    def __init__(self, shared):
        self._shared = shared

    async def get_from_shared(self, key):
        return self._shared.get(key)


class _FakeAgent:
    def __init__(self, shared, profile):
        self.memory = _FakeMemory(shared)
        self._profile = profile

    async def _load_founder_profile_context(self):
        return self._profile


@pytest.mark.asyncio
async def test_snapshot_collects_full_surface():
    agent = _FakeAgent(
        shared={
            "current_plan": "Ship Notion adapter",
            "last_orchestration": json.dumps({"summary": "prev"}),
            "research_findings": "market is hot",
        },
        profile="<founder_business_context>Acme</founder_business_context>",
    )
    ctx = await snapshot_context(agent)
    assert "Acme" in ctx["company_context"]
    assert "Ship Notion adapter" in ctx["task_context"]
    assert "market is hot" in ctx["task_context"]
    assert set(ctx) == {"profile_context", "company_context", "task_context", "memory_context"}


@pytest.mark.asyncio
async def test_hydrate_returns_only_volatile_keys():
    agent = _FakeAgent(shared={"current_plan": "new plan"}, profile="p")
    fresh = await hydrate_volatile(agent)
    assert set(fresh) == {"company_context", "task_context"}
    assert "new plan" in fresh["task_context"]


@pytest.mark.asyncio
async def test_snapshot_tolerates_loader_failure():
    class _Boom(_FakeAgent):
        async def _load_founder_profile_context(self):
            raise RuntimeError("db down")

    agent = _Boom(shared={}, profile="")
    ctx = await snapshot_context(agent)
    assert ctx["company_context"] == ""  # degrades gracefully, does not raise
    assert ctx["task_context"] == ""
