"""Unit tests for hydrate + synthesize nodes (Task 6)."""

from types import SimpleNamespace

import pytest

from app.agents.graph.nodes import make_synthesize_node, make_hydrate_node
from app.agents.graph.state import new_state


class _FakeLLM:
    def __init__(self):
        self.calls = []

    async def generate(self, messages, *, system="", model=None, temperature=0.7,
                       max_tokens=4096, **kw):
        self.calls.append({"model": model, "prompt": messages[0].content})
        return SimpleNamespace(content="FINAL ANSWER", usage=SimpleNamespace(total=20))


class _Deps:
    def __init__(self):
        self.llm = _FakeLLM()
        self.main_model = "main"

    async def hydrate(self):
        return {"company_context": "fresh-co", "task_context": "fresh-task"}


@pytest.mark.asyncio
async def test_synthesize_produces_final_answer():
    deps = _Deps()
    node = make_synthesize_node(deps)
    state = new_state("u", "s", "help me")
    state["results"] = {"research": "r", "planner": "p"}
    out = await node(state)
    assert out["final_answer"] == "FINAL ANSWER"
    assert out["trace"][-1] == {"node": "synthesize", "tokens_used": 20}
    # used the main tier and included specialist outputs
    assert deps.llm.calls[0]["model"] == "main"
    assert "r" in deps.llm.calls[0]["prompt"] and "p" in deps.llm.calls[0]["prompt"]


@pytest.mark.asyncio
async def test_synthesize_handles_no_results():
    node = make_synthesize_node(_Deps())
    out = await node(new_state("u", "s", "hi"))
    assert out["final_answer"] == "FINAL ANSWER"  # (none) path does not crash


@pytest.mark.asyncio
async def test_hydrate_refreshes_volatile_context():
    node = make_hydrate_node(_Deps())
    out = await node(new_state("u", "s", "x"))
    assert out == {"company_context": "fresh-co", "task_context": "fresh-task"}
