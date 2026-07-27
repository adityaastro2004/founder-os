"""Parity tests for OrchestratorAgent._result_from_state (Task 11).

This is the highest-risk piece of the in-place replacement: it maps the graph's
final state back to the ``AgentResult`` shape existing callers rely on
(``content`` / ``tokens_used`` / ``delegations``). Built via ``__new__`` to test
the mapper in isolation without the full agent constructor.
"""

from types import SimpleNamespace

from app.agents.orchestrator import OrchestratorAgent, OrchestrationTrace


def _agent():
    a = OrchestratorAgent.__new__(OrchestratorAgent)
    a._trace = OrchestrationTrace()
    a.config = SimpleNamespace(model="test-model")
    a.session_id = "sess1"
    return a


def test_maps_final_answer_and_tokens():
    a = _agent()
    final = {
        "final_answer": "Here is your plan.",
        "results": {"planner": "the plan", "research": "the findings"},
        "trace": [
            {"node": "classify", "tokens_used": 5},
            {"agent": "research", "success": True, "tokens_used": 10, "error": ""},
            {"agent": "planner", "success": True, "tokens_used": 20, "error": ""},
            {"node": "synthesize", "tokens_used": 30},
        ],
    }
    result = a._result_from_state(final, start=0.0)
    assert result.content == "Here is your plan."
    assert result.tokens_used == 65  # 5 + 10 + 20 + 30
    assert result.model == "test-model"
    assert {d.to_agent for d in result.delegations} == {"research", "planner"}
    assert set(a._trace.agents_used) == {"research", "planner"}
    assert a._trace.total_delegations == 2


def test_failed_delegation_recorded_but_not_in_agents_used():
    a = _agent()
    final = {
        "final_answer": "partial",
        "results": {"planner": ""},
        "trace": [{"agent": "planner", "success": False, "tokens_used": 0, "error": "boom"}],
    }
    result = a._result_from_state(final, start=0.0)
    assert len(result.delegations) == 1
    assert result.delegations[0].success is False
    assert result.delegations[0].error == "boom"
    assert a._trace.agents_used == []  # failures don't count as used


def test_interrupt_surfaces_pending_approval():
    a = _agent()
    final = {"__interrupt__": ({"reason": "approval_required"},)}
    result = a._result_from_state(final, start=0.0)
    assert result.content == ""
    assert result.pending_approvals
    assert result.pending_approvals[0]["reason"] == "approval_required"
    assert result.pending_approvals[0]["session_id"] == "sess1"


def test_empty_state_does_not_crash():
    a = _agent()
    result = a._result_from_state({}, start=0.0)
    assert result.content == ""
    assert result.tokens_used == 0
    assert result.delegations == []
