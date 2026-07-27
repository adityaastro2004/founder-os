"""Durability tests for the orchestrator graph (Task 11).

Uses LangGraph's in-process ``MemorySaver`` so these run in the unit tier (no
Postgres). They prove the two durability behaviors the design promises:

1. A run pauses at the approval interrupt and resumes with the founder's answer.
2. On resume, an already-completed specialist is NOT re-run (its output is loaded
   from the checkpoint) — the crash-resume / token-saving guarantee.
3. ``hydrate`` refreshes volatile context after the pause (stale-context policy).
"""

import json
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.agents.graph.orchestrator_graph import build_graph
from app.agents.graph.state import new_state


class _LLM:
    def __init__(self, intent, agents, needs_approval):
        self._decision = {"intent": intent, "agents": agents, "needs_approval": needs_approval}

    async def generate(self, messages, *, system="", model=None, **kw):
        if "routing classifier" in system:
            return SimpleNamespace(content=json.dumps(self._decision),
                                   usage=SimpleNamespace(total=1))
        return SimpleNamespace(content="FINAL", usage=SimpleNamespace(total=2))


class _CountingRouter:
    def __init__(self):
        self.calls = []

    async def delegate(self, message, *, user_id=None, session_id=None):
        self.calls.append(message.to_agent)
        return SimpleNamespace(content=f"{message.to_agent}-out", success=True,
                               error="", tokens_used=3)


class _Deps:
    def __init__(self, intent="MULTI_STEP", agents=("planner",), needs_approval=True):
        self.llm = _LLM(intent, list(agents), needs_approval)
        self.router = _CountingRouter()
        self.event_bus = None
        self.user_id = "u"
        self.session_id = "t1"
        self.cheap_model = None
        self.main_model = None
        self.hydrate_calls = 0

    async def snapshot(self):
        return {"profile_context": "", "company_context": "stale",
                "task_context": "stale", "memory_context": ""}

    async def hydrate(self):
        self.hydrate_calls += 1
        return {"company_context": "fresh", "task_context": "fresh"}


@pytest.mark.asyncio
async def test_run_pauses_at_approval_then_resumes():
    deps = _Deps(needs_approval=True)
    graph = build_graph(deps, checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t1"}}

    paused = await graph.ainvoke(new_state("u", "t1", "delete prod"), config=cfg)
    # interrupted — no final answer yet
    assert "__interrupt__" in paused
    assert paused.get("final_answer", "") == ""

    resumed = await graph.ainvoke(Command(resume="approved"), config=cfg)
    assert resumed["final_answer"] == "FINAL"
    assert resumed["approval_answer"] == "approved"


@pytest.mark.asyncio
async def test_specialist_not_rerun_on_resume():
    deps = _Deps(agents=("planner",), needs_approval=True)
    graph = build_graph(deps, checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t1"}}

    await graph.ainvoke(new_state("u", "t1", "do X"), config=cfg)   # runs planner, pauses
    await graph.ainvoke(Command(resume="approved"), config=cfg)     # resumes past planner

    # planner ran exactly once across the pause/resume boundary
    assert deps.router.calls.count("planner") == 1


@pytest.mark.asyncio
async def test_hydrate_refreshes_context_after_resume():
    deps = _Deps(needs_approval=True)
    graph = build_graph(deps, checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t1"}}

    await graph.ainvoke(new_state("u", "t1", "x"), config=cfg)
    resumed = await graph.ainvoke(Command(resume="ok"), config=cfg)

    # hydrate ran and the snapshot's stale context was refreshed before synthesis
    assert deps.hydrate_calls == 1
    assert resumed["company_context"] == "fresh"


@pytest.mark.asyncio
async def test_no_approval_completes_in_one_pass():
    deps = _Deps(agents=("planner",), needs_approval=False)
    graph = build_graph(deps, checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t2"}}

    out = await graph.ainvoke(new_state("u", "t2", "just plan"), config=cfg)
    assert "__interrupt__" not in out
    assert out["final_answer"] == "FINAL"
    assert deps.router.calls == ["planner"]
