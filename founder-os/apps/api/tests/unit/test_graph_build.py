"""Unit tests for assembling + compiling the orchestrator graph (Task 7).

These run the whole graph end-to-end with fakes and no checkpointer, exercising
the real edges/nodes wiring.
"""

import json
from types import SimpleNamespace

import pytest

from app.agents.graph.orchestrator_graph import build_graph, checkpointer_dsn
from app.agents.graph.state import new_state


class _LLM:
    """Returns a classify JSON when called as the classifier, else a synth answer."""

    def __init__(self, intent="SIMPLE", agents=None, needs_approval=False):
        self._decision = {
            "intent": intent,
            "agents": agents or [],
            "needs_approval": needs_approval,
        }

    async def generate(self, messages, *, system="", model=None, **kw):
        if "routing classifier" in system:
            return SimpleNamespace(content=json.dumps(self._decision),
                                   usage=SimpleNamespace(total=1))
        return SimpleNamespace(content="SYNTH", usage=SimpleNamespace(total=2))


class _Router:
    def __init__(self):
        self.calls = []

    async def delegate(self, message, *, user_id=None, session_id=None):
        self.calls.append(message.to_agent)
        return SimpleNamespace(content=f"{message.to_agent}-out", success=True,
                               error="", tokens_used=3)


class _Deps:
    def __init__(self, llm, router=None):
        self.llm = llm
        self.router = router or _Router()
        self.event_bus = None
        self.user_id = "u"
        self.session_id = "s"
        self.cheap_model = None
        self.main_model = None

    async def snapshot(self):
        return {"profile_context": "", "company_context": "c",
                "task_context": "", "memory_context": ""}

    async def hydrate(self):
        return {"company_context": "c-fresh", "task_context": ""}


def test_checkpointer_dsn_strips_asyncpg():
    settings = SimpleNamespace(DATABASE_URL="postgresql+asyncpg://a:b@h:5432/db")
    assert checkpointer_dsn(settings) == "postgresql://a:b@h:5432/db"


@pytest.mark.asyncio
async def test_simple_request_goes_straight_to_synthesize():
    deps = _Deps(_LLM(intent="SIMPLE", agents=[]))
    graph = build_graph(deps)
    out = await graph.ainvoke(new_state("u", "s", "hello"))
    assert out["final_answer"] == "SYNTH"
    assert deps.router.calls == []  # no specialists for an empty plan


@pytest.mark.asyncio
async def test_multistep_runs_specialists_then_synthesizes():
    deps = _Deps(_LLM(intent="MULTI_STEP", agents=["research", "planner"]))
    graph = build_graph(deps)
    out = await graph.ainvoke(new_state("u", "s", "research + plan"))
    assert deps.router.calls == ["research", "planner"]
    assert out["results"]["research"] == "research-out"
    assert out["final_answer"] == "SYNTH"


@pytest.mark.asyncio
async def test_hydrate_runs_before_synthesize():
    deps = _Deps(_LLM(intent="MULTI_STEP", agents=["planner"]))
    graph = build_graph(deps)
    out = await graph.ainvoke(new_state("u", "s", "x"))
    # hydrate refreshed company_context before synthesize
    assert out["company_context"] == "c-fresh"
