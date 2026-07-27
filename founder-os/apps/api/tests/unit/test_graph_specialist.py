"""Unit tests for the specialist fanout node (Task 5)."""

import pytest

from app.agents.graph.nodes import make_fanout_node
from app.agents.graph.state import new_state


class _Result:
    def __init__(self, content, ok=True):
        self.content = content
        self.success = ok
        self.error = "" if ok else "boom"
        self.tokens_used = 5


class _FakeRouter:
    def __init__(self):
        self.calls = []

    async def delegate(self, message, *, user_id=None, session_id=None):
        self.calls.append(message.to_agent)
        return _Result(f"{message.to_agent}-output")


class _FakeBus:
    def __init__(self):
        self.events = []

    async def publish(self, event):
        self.events.append(event)


class _Deps:
    def __init__(self):
        self.router = _FakeRouter()
        self.event_bus = _FakeBus()
        self.user_id = "u"
        self.session_id = "s"


def _state(agents, **over):
    s = new_state("u", "s", "do the thing")
    s["planned_agents"] = agents
    s.update(over)
    return s


@pytest.mark.asyncio
async def test_fanout_runs_pending_and_emits_events():
    deps = _Deps()
    node = make_fanout_node(deps)
    out = await node(_state(["research", "planner"]))
    assert out["results"]["research"] == "research-output"
    assert out["results"]["planner"] == "planner-output"
    types = [e.type for e in deps.event_bus.events]
    assert "delegation.executing" in types
    assert "delegation.completed" in types
    assert deps.router.calls == ["research", "planner"]


@pytest.mark.asyncio
async def test_fanout_skips_already_completed():
    deps = _Deps()
    node = make_fanout_node(deps)
    out = await node(_state(["research", "planner"], results={"research": "cached"}))
    # research not re-run; planner run
    assert deps.router.calls == ["planner"]
    assert out["results"]["research"] == "cached"


@pytest.mark.asyncio
async def test_fanout_records_delegate_failure_without_raising():
    deps = _Deps()

    async def _fail(message, *, user_id=None, session_id=None):
        return _Result("", ok=False)

    deps.router.delegate = _fail
    node = make_fanout_node(deps)
    out = await node(_state(["planner"]))
    assert "planner" in out["results"]  # recorded (empty), not dropped
    assert out["results"]["planner"] == ""
    assert any(e.type == "delegation.failed" for e in deps.event_bus.events)


@pytest.mark.asyncio
async def test_fanout_survives_router_exception():
    deps = _Deps()

    async def _boom(message, *, user_id=None, session_id=None):
        raise RuntimeError("router exploded")

    deps.router.delegate = _boom
    node = make_fanout_node(deps)
    out = await node(_state(["planner"]))
    assert out["results"]["planner"] == ""
    assert any(e.type == "delegation.failed" for e in deps.event_bus.events)


@pytest.mark.asyncio
async def test_fanout_forwards_context_to_specialist():
    deps = _Deps()
    captured = {}

    async def _capture(message, *, user_id=None, session_id=None):
        captured["task"] = message.task
        return _Result("ok")

    deps.router.delegate = _capture
    node = make_fanout_node(deps)
    s = _state(["planner"], company_context="Acme Inc", task_context="Ship v2")
    await node(s)
    assert "Acme Inc" in captured["task"]
    assert "Ship v2" in captured["task"]
