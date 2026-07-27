"""Unit tests for deterministic routing edges (Task 4)."""

from app.agents.graph.edges import route_after_classify, pending_agents
from app.agents.graph.state import new_state


def _st(**over):
    s = new_state("u", "s", "x")
    s.update(over)
    return s


def test_complex_routes_to_llm_router():
    assert route_after_classify(_st(intent="COMPLEX")) == "llm_route"


def test_complex_wins_even_with_planned_agents():
    assert route_after_classify(_st(intent="COMPLEX", planned_agents=["planner"])) == "llm_route"


def test_plan_routes_to_fanout():
    assert route_after_classify(_st(intent="MULTI_STEP", planned_agents=["planner"])) == "fanout"


def test_empty_plan_routes_to_synthesize():
    assert route_after_classify(_st(intent="SIMPLE", planned_agents=[])) == "synthesize"


def test_pending_excludes_completed():
    s = _st(planned_agents=["research", "planner"], results={"research": "done"})
    assert pending_agents(s) == ["planner"]


def test_pending_all_when_none_done():
    s = _st(planned_agents=["research", "planner"])
    assert pending_agents(s) == ["research", "planner"]
