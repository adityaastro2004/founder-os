"""Unit tests for the OrchestratorAgent → graph adapter plumbing (Task 8)."""

import pytest

from app.agents.graph.deps import GraphDeps


class _Mem:
    async def get_from_shared(self, k):
        return None

    async def save_to_shared(self, k, v):
        pass


class _Agent:
    """Minimal stand-in exposing the attributes GraphDeps.from_agent reads."""

    def __init__(self):
        self.router = object()
        self.event_bus = object()
        self.memory = _Mem()
        self.user_id = "u"
        self.session_id = "s"
        self.llm = object()

    async def _load_founder_profile_context(self):
        return "profile-block"


@pytest.mark.asyncio
async def test_graphdeps_from_agent_binds_collaborators():
    agent = _Agent()
    deps = GraphDeps.from_agent(agent, cheap_model="cheap", main_model="main")
    assert deps.llm is agent.llm
    assert deps.router is agent.router
    assert deps.event_bus is agent.event_bus
    assert deps.user_id == "u"
    assert deps.session_id == "s"
    assert deps.cheap_model == "cheap"
    assert deps.main_model == "main"


@pytest.mark.asyncio
async def test_graphdeps_snapshot_and_hydrate_delegate_to_agent():
    deps = GraphDeps.from_agent(_Agent())
    snap = await deps.snapshot()
    assert snap["company_context"] == "profile-block"
    assert set(snap) == {"profile_context", "company_context", "task_context", "memory_context"}
    hy = await deps.hydrate()
    assert set(hy) == {"company_context", "task_context"}


@pytest.mark.asyncio
async def test_graphdeps_tolerates_missing_session_id():
    agent = _Agent()
    del agent.session_id
    deps = GraphDeps.from_agent(agent)
    assert deps.session_id == ""
