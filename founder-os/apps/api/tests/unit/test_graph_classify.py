"""Unit tests for the classify node (Task 3).

The fake LLM matches the real ``LLMProvider.generate`` signature: it accepts
``system`` / ``model`` / ``temperature`` / ``max_tokens`` and returns an object
with ``.content`` and ``.usage.total``.
"""

import json
from types import SimpleNamespace

import pytest

from app.agents.graph.nodes import make_classify_node
from app.agents.graph.state import new_state


class _FakeLLM:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    async def generate(self, messages, *, system="", model=None, temperature=0.7,
                       max_tokens=4096, **kw):
        self.calls.append({"model": model, "system": system})
        content = self._payload if isinstance(self._payload, str) else json.dumps(self._payload)
        return SimpleNamespace(content=content, usage=SimpleNamespace(total=12))


class _Deps:
    def __init__(self, llm):
        self.llm = llm
        self.cheap_model = "cheap"

    async def snapshot(self):
        return {
            "profile_context": "p",
            "company_context": "c",
            "task_context": "t",
            "memory_context": "m",
        }


@pytest.mark.asyncio
async def test_classify_returns_plan_and_context():
    llm = _FakeLLM({"intent": "MULTI_STEP", "agents": ["research", "planner"],
                    "needs_approval": False})
    node = make_classify_node(_Deps(llm))
    out = await node(new_state("u", "s", "plan my launch"))
    assert out["intent"] == "MULTI_STEP"
    assert out["planned_agents"] == ["research", "planner"]
    assert out["needs_approval"] is False
    # context surface merged into the state update
    assert out["company_context"] == "c"
    assert out["memory_context"] == "m"
    # used the cheap tier
    assert llm.calls[0]["model"] == "cheap"


@pytest.mark.asyncio
async def test_classify_drops_unknown_agents():
    node = make_classify_node(_Deps(_FakeLLM(
        {"intent": "SIMPLE", "agents": ["bogus", "planner"], "needs_approval": False})))
    out = await node(new_state("u", "s", "x"))
    assert out["planned_agents"] == ["planner"]


@pytest.mark.asyncio
async def test_classify_defaults_on_bad_json():
    node = make_classify_node(_Deps(_FakeLLM("not json at all")))
    out = await node(new_state("u", "s", "x"))
    assert out["intent"] == "SIMPLE"
    assert out["planned_agents"] == []
    assert out["needs_approval"] is False


@pytest.mark.asyncio
async def test_classify_records_tokens_in_trace():
    node = make_classify_node(_Deps(_FakeLLM(
        {"intent": "SIMPLE", "agents": ["planner"], "needs_approval": False})))
    out = await node(new_state("u", "s", "x"))
    assert out["trace"][-1] == {"node": "classify", "tokens_used": 12, "intent": "SIMPLE"}
