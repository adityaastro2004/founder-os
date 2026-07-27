"""Unit tests for the orchestrator graph state factory (Task 1)."""

from app.agents.graph.state import OrchestratorState, new_state


def test_new_state_defaults():
    s = new_state("u1", "sess1", "hello", extra_context="ctx")
    assert s["user_id"] == "u1"
    assert s["session_id"] == "sess1"
    assert s["user_input"] == "hello"
    assert s["extra_context"] == "ctx"
    # working state starts empty / neutral
    assert s["results"] == {}
    assert s["planned_agents"] == []
    assert s["intent"] == ""
    assert s["needs_approval"] is False
    assert s["approval_answer"] is None
    assert s["final_answer"] == ""
    assert s["trace"] == []
    # context surface present and empty
    for key in ("profile_context", "company_context", "task_context", "memory_context"):
        assert key in s and s[key] == ""


def test_new_state_query_embedding_optional():
    s = new_state("u", "s", "x")
    assert s["query_embedding"] is None
    s2 = new_state("u", "s", "x", query_embedding=[0.1, 0.2])
    assert s2["query_embedding"] == [0.1, 0.2]


def test_state_is_typeddict_instance():
    # OrchestratorState is a plain dict at runtime
    s = new_state("u", "s", "x")
    assert isinstance(s, dict)
    assert set(OrchestratorState.__annotations__) == set(s.keys())
