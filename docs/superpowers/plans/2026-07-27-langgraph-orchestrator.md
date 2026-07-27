# LangGraph Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the orchestrator's in-memory LLM control loop with a durable LangGraph `StateGraph` that checkpoints to Postgres, routes cheaply via a classifier + deterministic edges, and carries the full company/task/memory context — without touching specialists, tools, memory, the event bus, or the 3-tier provider fallback.

**Architecture:** `OrchestratorAgent.run()` becomes a thin adapter that builds a compiled `StateGraph` from the agent's existing `self.router / self.memory / self.llm / self.event_bus / self.approval_gate` and invokes it with `thread_id = session_id`. Graph nodes are plain async closures that call existing code. Durability comes from `AsyncPostgresSaver`; token savings from one cheap-tier `classify` call + zero-token conditional edges; correctness across pause/resume from a `hydrate_context` node that refreshes volatile state.

**Tech Stack:** Python 3.14, FastAPI, LangGraph (`langgraph`, `langgraph-checkpoint-postgres`), psycopg3, Postgres 16, existing `app/agents/*` code, pytest + pytest-asyncio.

## Global Constraints

- **Python floor:** 3.14 (async-first). Every module uses `from __future__ import annotations`.
- **No LangChain chat models.** Only `StateGraph`, `AsyncPostgresSaver`, and `interrupt` are imported from LangGraph. LLM calls go through the existing `LLMProvider` (`self.llm`) — never `langchain_*` model classes.
- **Provider fallback untouched:** all model calls use `self.llm` ([llm.py](../../founder-os/apps/api/app/agents/llm.py)); the "cheap tier" is expressed by passing a cheap `model=` to `self.llm`, not a new provider.
- **Event contract is frozen:** nodes emit exactly the event types the current orchestrator emits — `orchestration.started/completed`, `delegation.starting/executing/completed/failed/retrying` — with the same `data` keys. Verified by parity tests.
- **Schema via Alembic (repo rule #8):** the checkpointer's `.setup()` DDL runs inside an Alembic migration, never ad-hoc at runtime.
- **No local Ollama:** unit tests MUST mock `self.llm`; live behavior is `-m live` (CI/EC2 only).
- **In-place rollout:** no runtime legacy fallback; the parity suite (Task 12) is the safety net and must be green before merge.
- **Checkpointer DSN:** derive a plain `postgresql://…` psycopg3 DSN from `settings.DATABASE_URL` (strip the `+asyncpg`); do NOT reuse the asyncpg engine.

---

### Task 0: Dependency spike — verify LangGraph installs on Python 3.14

De-risks the whole plan. LangGraph + psycopg3 on Python 3.14 is bleeding-edge; confirm before writing code.

**Files:**
- Modify: `founder-os/apps/api/requirements.txt`

- [ ] **Step 1: Attempt install in the venv**

Run:
```bash
cd founder-os/apps/api && source .venv/bin/activate && \
pip install "langgraph>=0.2.60" "langgraph-checkpoint-postgres>=2.0.0" "psycopg[binary]>=3.2.0"
```
Expected: resolves and installs on Python 3.14. If it fails on 3.14, STOP and report — this changes the plan (pin an older LangGraph, or containerize the checkpointer).

- [ ] **Step 2: Verify the three imports work**

Run:
```bash
python -c "from langgraph.graph import StateGraph; from langgraph.types import interrupt; from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver; print('ok')"
```
Expected: prints `ok`. (If `interrupt` is not in `langgraph.types` for the pinned version, locate it via `python -c "import langgraph; help(langgraph)"` and record the correct import path in this plan before proceeding.)

- [ ] **Step 3: Pin the resolved versions in requirements.txt**

Add under a new `# Orchestration graph` section, using the exact versions `pip freeze | grep -Ei 'langgraph|psycopg'` reports:
```
# Orchestration graph
langgraph>=0.2.60
langgraph-checkpoint-postgres>=2.0.0
psycopg[binary]>=3.2.0
```

- [ ] **Step 4: Commit**

```bash
git add founder-os/apps/api/requirements.txt
git commit -m "build: add langgraph + psycopg3 for durable orchestrator"
```

---

### Task 1: Orchestrator graph state

**Files:**
- Create: `founder-os/apps/api/app/agents/graph/__init__.py`
- Create: `founder-os/apps/api/app/agents/graph/state.py`
- Test: `founder-os/apps/api/tests/unit/test_graph_state.py`

**Interfaces:**
- Produces: `OrchestratorState` (TypedDict) and `new_state(user_id, session_id, user_input, *, query_embedding=None, extra_context="") -> OrchestratorState` — the initial-state factory every node and the adapter rely on.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_graph_state.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_graph_state.py -v`
Expected: FAIL — `ModuleNotFoundError: app.agents.graph.state`.

- [ ] **Step 3: Write minimal implementation**

```python
# app/agents/graph/__init__.py
"""LangGraph-based durable orchestrator (see docs/superpowers/specs/2026-07-27-langgraph-orchestrator-design.md)."""
```

```python
# app/agents/graph/state.py
from __future__ import annotations

from typing import TypedDict


class OrchestratorState(TypedDict):
    user_id: str
    session_id: str
    user_input: str
    query_embedding: list[float] | None

    # context surface (mirrors base.py injection)
    profile_context: str
    company_context: str
    task_context: str
    memory_context: str
    extra_context: str

    # working state — accumulates across nodes so resume never re-pays
    intent: str
    planned_agents: list[str]
    results: dict[str, str]
    needs_approval: bool
    approval_answer: str | None
    final_answer: str
    trace: list[dict]


def new_state(
    user_id: str,
    session_id: str,
    user_input: str,
    *,
    query_embedding: list[float] | None = None,
    extra_context: str = "",
) -> OrchestratorState:
    return OrchestratorState(
        user_id=user_id,
        session_id=session_id,
        user_input=user_input,
        query_embedding=query_embedding,
        profile_context="",
        company_context="",
        task_context="",
        memory_context="",
        extra_context=extra_context,
        intent="",
        planned_agents=[],
        results={},
        needs_approval=False,
        approval_answer=None,
        final_answer="",
        trace=[],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_graph_state.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/agents/graph/__init__.py app/agents/graph/state.py tests/unit/test_graph_state.py
git commit -m "feat(graph): orchestrator state model + factory"
```

---

### Task 2: Context snapshot & hydrate helpers

Reuses the orchestrator's existing memory/profile loaders to fill the context surface. Because the orchestrator already loads founder profile and shared memory in `base.py`, these helpers read from `agent.memory` (shared/working) and the profile loader — no new data sources.

**Files:**
- Create: `founder-os/apps/api/app/agents/graph/context.py`
- Test: `founder-os/apps/api/tests/unit/test_graph_context.py`

**Interfaces:**
- Consumes: an object exposing `memory` (with async `get_from_shared(key)`) and `_load_founder_profile_context()` — the `OrchestratorAgent` satisfies both.
- Produces:
  - `async snapshot_context(agent) -> dict[str, str]` returning keys `profile_context, company_context, task_context, memory_context`.
  - `async hydrate_volatile(agent) -> dict[str, str]` returning refreshed `company_context, task_context` only (profile/memory trusted from checkpoint).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_graph_context.py
import json
import pytest
from app.agents.graph.context import snapshot_context, hydrate_volatile


class _FakeMemory:
    def __init__(self, shared): self._shared = shared
    async def get_from_shared(self, key): return self._shared.get(key)


class _FakeAgent:
    def __init__(self, shared, profile):
        self.memory = _FakeMemory(shared)
        self._profile = profile
    async def _load_founder_profile_context(self): return self._profile


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_graph_context.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# app/agents/graph/context.py
from __future__ import annotations

from typing import Any


async def _shared(agent: Any, key: str) -> str:
    try:
        val = await agent.memory.get_from_shared(key)
        return str(val) if val else ""
    except Exception:
        return ""


async def _task_context(agent: Any) -> str:
    parts = []
    for key in ("current_plan", "research_findings", "last_orchestration"):
        val = await _shared(agent, key)
        if val:
            parts.append(f"<{key}>\n{val}\n</{key}>")
    return "\n".join(parts)


async def snapshot_context(agent: Any) -> dict[str, str]:
    """Point-in-time read of the full context surface (used at classify time)."""
    try:
        profile = await agent._load_founder_profile_context()
    except Exception:
        profile = ""
    return {
        "profile_context": profile,
        "company_context": profile,  # business context lives in the profile block today
        "task_context": await _task_context(agent),
        "memory_context": "",  # <memories> recall is injected by base.py at run time
    }


async def hydrate_volatile(agent: Any) -> dict[str, str]:
    """Refresh only the fast-changing context (company/task) before synthesis / on resume."""
    try:
        profile = await agent._load_founder_profile_context()
    except Exception:
        profile = ""
    return {
        "company_context": profile,
        "task_context": await _task_context(agent),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_graph_context.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/agents/graph/context.py tests/unit/test_graph_context.py
git commit -m "feat(graph): context snapshot + volatile re-hydration helpers"
```

---

### Task 3: Classify node (cheap-tier routing decision)

**Files:**
- Create: `founder-os/apps/api/app/agents/graph/nodes.py`
- Test: `founder-os/apps/api/tests/unit/test_graph_classify.py`

**Interfaces:**
- Consumes: `OrchestratorState`; a `deps` object carrying `llm` (an `LLMProvider`) and `cheap_model: str | None`.
- Produces: `make_classify_node(deps) -> callable(state) -> dict` — returns a partial-state update `{intent, planned_agents, needs_approval, company_context, task_context, profile_context, memory_context}`. Valid agent names: `planner, research, content, support`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_graph_classify.py
import json
import pytest
from app.agents.graph.nodes import make_classify_node
from app.agents.graph.state import new_state


class _FakeLLM:
    def __init__(self, payload): self._payload = payload
    async def complete(self, messages, *, model=None, **kw):
        from types import SimpleNamespace
        return SimpleNamespace(content=json.dumps(self._payload), tokens_used=12)


class _Deps:
    def __init__(self, llm):
        self.llm = llm
        self.cheap_model = "cheap"
    async def snapshot(self): return {
        "profile_context": "p", "company_context": "c",
        "task_context": "t", "memory_context": "m",
    }


@pytest.mark.asyncio
async def test_classify_returns_plan_and_context():
    deps = _Deps(_FakeLLM({"intent": "MULTI_STEP",
                           "agents": ["research", "planner"],
                           "needs_approval": False}))
    node = make_classify_node(deps)
    out = await node(new_state("u", "s", "plan my launch"))
    assert out["intent"] == "MULTI_STEP"
    assert out["planned_agents"] == ["research", "planner"]
    assert out["needs_approval"] is False
    assert out["company_context"] == "c"


@pytest.mark.asyncio
async def test_classify_drops_unknown_agents():
    deps = _Deps(_FakeLLM({"intent": "SIMPLE", "agents": ["bogus", "planner"], "needs_approval": False}))
    node = make_classify_node(deps)
    out = await node(new_state("u", "s", "x"))
    assert out["planned_agents"] == ["planner"]
```

Note: match `complete()` to the real `LLMProvider` signature — verify in [llm.py](../../founder-os/apps/api/app/agents/llm.py) at Step 3 and adjust the fake if the method name/kwargs differ.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_graph_classify.py -v`
Expected: FAIL — module/function missing.

- [ ] **Step 3: Write minimal implementation**

First confirm the provider call signature:
Run: `grep -n "async def complete\|def complete\|class LLMMessage\|class Role" app/agents/llm.py | head`
Then implement (adjust `complete(...)` call + message construction to the real signature):

```python
# app/agents/graph/nodes.py
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

VALID_AGENTS = {"planner", "research", "content", "support"}

_CLASSIFY_PROMPT = """You are a routing classifier for a founder's AI operations \
system. Given the request and the company/task context, return STRICT JSON:
{{"intent": "SIMPLE|MULTI_STEP|COMPLEX", "agents": [<subset of planner,research,content,support>], "needs_approval": <bool>}}
- SIMPLE: one specialist. MULTI_STEP: 2-3 in sequence. COMPLEX: ambiguous, needs an LLM router.
- needs_approval: true only if the request implies a destructive or high-stakes action.
Company context:\n{company}\nTask context:\n{task}\nRequest:\n{request}\nJSON:"""


def _parse_classify(raw: str) -> dict:
    start, end = raw.find("{"), raw.rfind("}")
    data = json.loads(raw[start : end + 1]) if start != -1 else {}
    agents = [a for a in data.get("agents", []) if a in VALID_AGENTS]
    return {
        "intent": data.get("intent", "SIMPLE") or "SIMPLE",
        "planned_agents": agents,
        "needs_approval": bool(data.get("needs_approval", False)),
    }


def make_classify_node(deps: Any):
    async def classify(state) -> dict:
        ctx = await deps.snapshot()
        prompt = _CLASSIFY_PROMPT.format(
            company=ctx["company_context"], task=ctx["task_context"],
            request=state["user_input"],
        )
        from app.agents.llm import LLMMessage, Role
        resp = await deps.llm.complete(
            [LLMMessage(role=Role.USER, content=prompt)],
            model=deps.cheap_model,
        )
        parsed = _parse_classify(resp.content)
        return {**parsed, **ctx}
    return classify
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_graph_classify.py -v`
Expected: PASS. Fix the fake/impl if the real `complete()` signature differs.

- [ ] **Step 5: Commit**

```bash
git add app/agents/graph/nodes.py tests/unit/test_graph_classify.py
git commit -m "feat(graph): cheap-tier classify node with structured routing"
```

---

### Task 4: Deterministic routing edges

**Files:**
- Create: `founder-os/apps/api/app/agents/graph/edges.py`
- Test: `founder-os/apps/api/tests/unit/test_graph_edges.py`

**Interfaces:**
- Produces:
  - `route_after_classify(state) -> str` — returns `"llm_route"` if `intent == "COMPLEX"`, else `"fanout"` if `planned_agents` non-empty, else `"synthesize"`.
  - `pending_agents(state) -> list[str]` — agents in `planned_agents` not yet in `results` (drives sequential specialist execution).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_graph_edges.py
from app.agents.graph.edges import route_after_classify, pending_agents
from app.agents.graph.state import new_state


def _st(**over):
    s = new_state("u", "s", "x"); s.update(over); return s


def test_complex_routes_to_llm_router():
    assert route_after_classify(_st(intent="COMPLEX")) == "llm_route"


def test_plan_routes_to_fanout():
    assert route_after_classify(_st(intent="MULTI_STEP", planned_agents=["planner"])) == "fanout"


def test_empty_plan_routes_to_synthesize():
    assert route_after_classify(_st(intent="SIMPLE", planned_agents=[])) == "synthesize"


def test_pending_excludes_completed():
    s = _st(planned_agents=["research", "planner"], results={"research": "done"})
    assert pending_agents(s) == ["planner"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_graph_edges.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# app/agents/graph/edges.py
from __future__ import annotations


def route_after_classify(state) -> str:
    if state["intent"] == "COMPLEX":
        return "llm_route"
    if state["planned_agents"]:
        return "fanout"
    return "synthesize"


def pending_agents(state) -> list[str]:
    done = set(state["results"])
    return [a for a in state["planned_agents"] if a not in done]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_graph_edges.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/agents/graph/edges.py tests/unit/test_graph_edges.py
git commit -m "feat(graph): zero-token deterministic routing edges"
```

---

### Task 5: Specialist node wrapper (delegation + event parity)

**Files:**
- Modify: `founder-os/apps/api/app/agents/graph/nodes.py`
- Test: `founder-os/apps/api/tests/unit/test_graph_specialist.py`

**Interfaces:**
- Consumes: `deps.router` (an `AgentRouter` with async `delegate(message, *, user_id, session_id)`), `deps.event_bus`, `deps.user_id`, `deps.session_id`.
- Produces: `make_fanout_node(deps) -> callable(state) -> dict` — runs each `pending_agents(state)` sequentially via the router, writes into `results`, appends `trace` entries, and publishes `delegation.executing` + `delegation.completed`/`delegation.failed` events with the SAME `data` keys as [orchestrator.py:482-533](../../founder-os/apps/api/app/agents/orchestrator.py#L482).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_graph_specialist.py
import pytest
from app.agents.graph.nodes import make_fanout_node
from app.agents.graph.state import new_state


class _Result:
    def __init__(self, content, ok=True):
        self.content, self.success, self.error, self.tokens_used = content, ok, "", 5


class _FakeRouter:
    def __init__(self): self.calls = []
    async def delegate(self, message, *, user_id=None, session_id=None):
        self.calls.append(message.to_agent)
        return _Result(f"{message.to_agent}-output")


class _FakeBus:
    def __init__(self): self.events = []
    async def publish(self, event): self.events.append(event)


class _Deps:
    def __init__(self):
        self.router, self.event_bus = _FakeRouter(), _FakeBus()
        self.user_id, self.session_id = "u", "s"


@pytest.mark.asyncio
async def test_fanout_runs_pending_and_emits_events():
    deps = _Deps()
    node = make_fanout_node(deps)
    state = new_state("u", "s", "x"); state["planned_agents"] = ["research", "planner"]
    out = await node(state)
    assert out["results"]["research"] == "research-output"
    assert out["results"]["planner"] == "planner-output"
    types = [e.type for e in deps.event_bus.events]
    assert "delegation.executing" in types and "delegation.completed" in types


@pytest.mark.asyncio
async def test_fanout_records_failure_without_raising():
    deps = _Deps()
    async def _boom(message, *, user_id=None, session_id=None): return _Result("", ok=False)
    deps.router.delegate = _boom
    node = make_fanout_node(deps)
    state = new_state("u", "s", "x"); state["planned_agents"] = ["planner"]
    out = await node(state)
    assert "planner" in out["results"]  # recorded (empty/failed), not dropped
    assert any(e.type == "delegation.failed" for e in deps.event_bus.events)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_graph_specialist.py -v`
Expected: FAIL — `make_fanout_node` missing.

- [ ] **Step 3: Write minimal implementation** (append to `nodes.py`)

```python
# append to app/agents/graph/nodes.py
from app.agents.graph.edges import pending_agents


def make_fanout_node(deps: Any):
    async def fanout(state) -> dict:
        from app.agents.event_bus import Event
        from app.agents.router import AgentMessage

        results = dict(state["results"])
        trace = list(state["trace"])
        context = "\n".join(
            state[k] for k in ("company_context", "task_context", "memory_context") if state.get(k)
        )
        for agent_name in pending_agents(state):
            if deps.event_bus:
                await deps.event_bus.publish(Event(
                    type="delegation.executing", agent=agent_name,
                    data={"from": "orchestrator", "task_preview": state["user_input"][:150],
                          "attempt": 1, "user_id": str(deps.user_id)},
                ))
            msg = AgentMessage(
                from_agent="orchestrator", to_agent=agent_name,
                task=f"{state['user_input']}\n\n<orchestrator_context>\n{context}\n</orchestrator_context>",
                context={"orchestrated": True},
            )
            try:
                dr = await deps.router.delegate(msg, user_id=deps.user_id, session_id=deps.session_id)
                results[agent_name] = dr.content if dr.success else ""
                trace.append({"agent": agent_name, "success": dr.success,
                              "tokens_used": dr.tokens_used, "error": dr.error})
                if deps.event_bus:
                    await deps.event_bus.publish(Event(
                        type="delegation.completed" if dr.success else "delegation.failed",
                        agent=agent_name,
                        data={"from": "orchestrator", "success": dr.success,
                              "tokens_used": dr.tokens_used, "result_preview": (dr.content or "")[:200],
                              "user_id": str(deps.user_id)},
                    ))
            except Exception as exc:  # never let one specialist crash the graph
                logger.exception("fanout delegation to %s failed", agent_name)
                results[agent_name] = ""
                trace.append({"agent": agent_name, "success": False, "error": str(exc)})
                if deps.event_bus:
                    await deps.event_bus.publish(Event(
                        type="delegation.failed", agent=agent_name,
                        data={"from": "orchestrator", "error": str(exc)[:300], "user_id": str(deps.user_id)},
                    ))
        return {"results": results, "trace": trace}
    return fanout
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_graph_specialist.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/agents/graph/nodes.py tests/unit/test_graph_specialist.py
git commit -m "feat(graph): specialist fanout node with event-bus parity"
```

---

### Task 6: Approval interrupt + hydrate_context + synthesize nodes

**Files:**
- Modify: `founder-os/apps/api/app/agents/graph/nodes.py`
- Test: `founder-os/apps/api/tests/unit/test_graph_synthesis.py`

**Interfaces:**
- Produces:
  - `make_hydrate_node(deps)` — returns `{company_context, task_context}` via `deps.hydrate()`.
  - `make_synthesize_node(deps)` — one main-tier `deps.llm.complete()` call over `results`; returns `{final_answer, trace}`.
  - `make_approval_node()` — calls `interrupt({...})`; on resume returns `{approval_answer: <resumed value>}`. (Only reached when `needs_approval`.)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_graph_synthesis.py
import pytest
from types import SimpleNamespace
from app.agents.graph.nodes import make_synthesize_node, make_hydrate_node
from app.agents.graph.state import new_state


class _FakeLLM:
    async def complete(self, messages, *, model=None, **kw):
        return SimpleNamespace(content="FINAL ANSWER", tokens_used=20)


class _Deps:
    def __init__(self):
        self.llm = _FakeLLM(); self.main_model = None
    async def hydrate(self): return {"company_context": "fresh-co", "task_context": "fresh-task"}


@pytest.mark.asyncio
async def test_synthesize_produces_final_answer():
    node = make_synthesize_node(_Deps())
    state = new_state("u", "s", "x"); state["results"] = {"research": "r", "planner": "p"}
    out = await node(state)
    assert out["final_answer"] == "FINAL ANSWER"


@pytest.mark.asyncio
async def test_hydrate_refreshes_volatile_context():
    node = make_hydrate_node(_Deps())
    out = await node(new_state("u", "s", "x"))
    assert out == {"company_context": "fresh-co", "task_context": "fresh-task"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_graph_synthesis.py -v`
Expected: FAIL — functions missing.

- [ ] **Step 3: Write minimal implementation** (append to `nodes.py`)

```python
# append to app/agents/graph/nodes.py
_SYNTH_PROMPT = """Synthesize a single coherent answer for the founder. Lead with the \
answer, weave specialist findings naturally (do not name the agents), list any actions \
with a checkmark, and end with 2-3 Next Steps.\nRequest:\n{request}\nCompany:\n{company}\n\
Specialist outputs:\n{results}\nAnswer:"""


def make_hydrate_node(deps: Any):
    async def hydrate(state) -> dict:
        return await deps.hydrate()
    return hydrate


def make_synthesize_node(deps: Any):
    async def synthesize(state) -> dict:
        from app.agents.llm import LLMMessage, Role
        joined = "\n\n".join(f"[{k}]\n{v}" for k, v in state["results"].items()) or "(none)"
        prompt = _SYNTH_PROMPT.format(request=state["user_input"],
                                      company=state["company_context"], results=joined)
        resp = await deps.llm.complete([LLMMessage(role=Role.USER, content=prompt)],
                                       model=getattr(deps, "main_model", None))
        trace = list(state["trace"]) + [{"node": "synthesize", "tokens_used": resp.tokens_used}]
        return {"final_answer": resp.content, "trace": trace}
    return synthesize


def make_approval_node():
    async def approval(state) -> dict:
        from langgraph.types import interrupt  # confirmed import path in Task 0 Step 2
        answer = interrupt({"reason": "approval_required", "request": state["user_input"]})
        return {"approval_answer": answer}
    return approval
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_graph_synthesis.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/agents/graph/nodes.py tests/unit/test_graph_synthesis.py
git commit -m "feat(graph): hydrate, synthesize, and approval-interrupt nodes"
```

---

### Task 7: Assemble & compile the StateGraph with the Postgres checkpointer

**Files:**
- Create: `founder-os/apps/api/app/agents/graph/orchestrator_graph.py`
- Test: `founder-os/apps/api/tests/unit/test_graph_build.py`

**Interfaces:**
- Consumes: all node/edge factories; a `deps` object (built in Task 8) exposing `llm, router, event_bus, user_id, session_id, cheap_model, main_model, snapshot(), hydrate()`.
- Produces:
  - `build_graph(deps) -> CompiledStateGraph` — wires `classify → (route_after_classify) → {llm_route|fanout|synthesize}`, `fanout → approval? → hydrate → synthesize → END`. Compiled WITHOUT a checkpointer (for unit tests).
  - `checkpointer_dsn(settings) -> str` — plain psycopg3 DSN derived from `settings.DATABASE_URL` (strip `+asyncpg`).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_graph_build.py
import pytest
from app.agents.graph.orchestrator_graph import build_graph, checkpointer_dsn


class _Deps:
    def __init__(self):
        self.llm = _L(); self.router = None; self.event_bus = None
        self.user_id = "u"; self.session_id = "s"
        self.cheap_model = None; self.main_model = None
    async def snapshot(self): return {"profile_context": "", "company_context": "c",
                                      "task_context": "", "memory_context": ""}
    async def hydrate(self): return {"company_context": "c", "task_context": ""}


class _L:
    async def complete(self, messages, *, model=None, **kw):
        from types import SimpleNamespace
        import json
        # classify returns SIMPLE with no agents so the graph goes straight to synth
        content = json.dumps({"intent": "SIMPLE", "agents": [], "needs_approval": False}) \
            if "classifier" in messages[0].content else "SYNTH"
        return SimpleNamespace(content=content, tokens_used=1)


def test_checkpointer_dsn_strips_asyncpg():
    dsn = checkpointer_dsn(type("S", (), {"DATABASE_URL": "postgresql+asyncpg://a:b@h:5432/db"}))
    assert dsn == "postgresql://a:b@h:5432/db"


@pytest.mark.asyncio
async def test_graph_runs_end_to_end_without_checkpointer():
    graph = build_graph(_Deps())
    from app.agents.graph.state import new_state
    out = await graph.ainvoke(new_state("u", "s", "hello"))
    assert out["final_answer"] == "SYNTH"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_graph_build.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# app/agents/graph/orchestrator_graph.py
from __future__ import annotations

from typing import Any

from langgraph.graph import StateGraph, END

from app.agents.graph.state import OrchestratorState
from app.agents.graph.edges import route_after_classify
from app.agents.graph.nodes import (
    make_classify_node, make_fanout_node, make_hydrate_node,
    make_synthesize_node, make_approval_node,
)


def checkpointer_dsn(settings: Any) -> str:
    return settings.DATABASE_URL.replace("+asyncpg", "")


def _route_after_fanout(state) -> str:
    return "approval" if state["needs_approval"] else "hydrate"


def build_graph(deps: Any):
    g = StateGraph(OrchestratorState)
    g.add_node("classify", make_classify_node(deps))
    g.add_node("llm_route", make_fanout_node(deps))  # v1: llm_route reuses fanout on planned_agents
    g.add_node("fanout", make_fanout_node(deps))
    g.add_node("approval", make_approval_node())
    g.add_node("hydrate", make_hydrate_node(deps))
    g.add_node("synthesize", make_synthesize_node(deps))

    g.set_entry_point("classify")
    g.add_conditional_edges("classify", route_after_classify,
                            {"llm_route": "llm_route", "fanout": "fanout", "synthesize": "synthesize"})
    g.add_conditional_edges("fanout", _route_after_fanout, {"approval": "approval", "hydrate": "hydrate"})
    g.add_edge("llm_route", "hydrate")
    g.add_edge("approval", "hydrate")
    g.add_edge("hydrate", "synthesize")
    g.add_edge("synthesize", END)
    return g.compile()
```

Note: in the test, make the classify prompt detectable — either assert on the real prompt text (`_CLASSIFY_PROMPT` contains "routing classifier") instead of "classifier", or adjust `_L.complete` to branch on `"JSON:" in messages[0].content`. Fix the fake to match the real prompt at Step 4.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_graph_build.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/agents/graph/orchestrator_graph.py tests/unit/test_graph_build.py
git commit -m "feat(graph): assemble + compile the orchestrator StateGraph"
```

---

### Task 8: Wire `OrchestratorAgent.run()` to the graph (in-place replacement)

**Files:**
- Modify: `founder-os/apps/api/app/agents/orchestrator.py`
- Create: `founder-os/apps/api/app/agents/graph/deps.py`
- Test: `founder-os/apps/api/tests/unit/test_orchestrator_graph_adapter.py`

**Interfaces:**
- Consumes: the compiled graph (Task 7); the agent's `self.router/memory/llm/event_bus/user_id`.
- Produces: `GraphDeps` (in `deps.py`) built from an `OrchestratorAgent`; a rewritten `OrchestratorAgent.run()` that builds initial state, invokes the graph with `config={"configurable": {"thread_id": session_id}}` and the app checkpointer, and returns an `AgentResult` with `.content = final_answer`, `.delegations` reconstructed from `trace`, and `.tokens_used` summed.

- [ ] **Step 1: Write the failing test** (adapter maps graph output → AgentResult)

```python
# tests/unit/test_orchestrator_graph_adapter.py
import pytest
from app.agents.graph.deps import GraphDeps


class _Mem:
    async def get_from_shared(self, k): return None
    async def save_to_shared(self, k, v): pass


class _Agent:
    def __init__(self):
        self.router = None; self.event_bus = None; self.memory = _Mem()
        self.user_id = "u"; self.session_id = "s"
        self.llm = None
    async def _load_founder_profile_context(self): return "profile"


@pytest.mark.asyncio
async def test_graphdeps_snapshot_and_hydrate():
    deps = GraphDeps.from_agent(_Agent(), cheap_model="cheap", main_model="main")
    snap = await deps.snapshot()
    assert snap["company_context"] == "profile"
    hy = await deps.hydrate()
    assert set(hy) == {"company_context", "task_context"}
    assert deps.cheap_model == "cheap" and deps.main_model == "main"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_orchestrator_graph_adapter.py -v`
Expected: FAIL — `app.agents.graph.deps` missing.

- [ ] **Step 3: Write minimal implementation**

```python
# app/agents/graph/deps.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.graph.context import snapshot_context, hydrate_volatile


@dataclass
class GraphDeps:
    llm: Any
    router: Any
    event_bus: Any
    memory: Any
    user_id: Any
    session_id: str
    cheap_model: str | None = None
    main_model: str | None = None
    _agent: Any = None

    @classmethod
    def from_agent(cls, agent, *, cheap_model=None, main_model=None) -> "GraphDeps":
        return cls(
            llm=agent.llm, router=agent.router, event_bus=agent.event_bus,
            memory=agent.memory, user_id=agent.user_id,
            session_id=getattr(agent, "session_id", "") or "",
            cheap_model=cheap_model, main_model=main_model, _agent=agent,
        )

    async def snapshot(self) -> dict[str, str]:
        return await snapshot_context(self._agent)

    async def hydrate(self) -> dict[str, str]:
        return await hydrate_volatile(self._agent)
```

Then rewrite `OrchestratorAgent.run()` in `orchestrator.py` (replace the `super().run(...)` body) to:
1. build `deps = GraphDeps.from_agent(self, cheap_model=<settings cheap model>, main_model=<default>)`,
2. `graph = build_graph(deps)` (checkpointer attached in Task 9 via a module-level app checkpointer; for now compile without so unit tests pass),
3. `final = await graph.ainvoke(new_state(str(self.user_id), self.session_id, user_input, extra_context=extra_context or ""), config={"configurable": {"thread_id": self.session_id or self.user_id}})`,
4. map to `AgentResult(content=final["final_answer"], ...)` and rebuild `result.delegations` from `final["trace"]` entries that have an `agent` key (preserve the existing `DelegationResult` shape used by [agent_routes.py:663](../../founder-os/apps/api/app/api/agent_routes.py#L663)).
Keep `after_run` persistence of `last_orchestration` intact.

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_orchestrator_graph_adapter.py tests/unit/ -k graph -v`
Expected: PASS. Then run the existing orchestrator regression: `pytest tests/regression -k orchestrat -v` and fix any signature drift.

- [ ] **Step 5: Commit**

```bash
git add app/agents/orchestrator.py app/agents/graph/deps.py tests/unit/test_orchestrator_graph_adapter.py
git commit -m "feat(graph): route OrchestratorAgent.run through the StateGraph (in-place)"
```

---

### Task 9: Checkpointer wiring + Alembic migration

**Files:**
- Modify: `founder-os/apps/api/app/agents/graph/orchestrator_graph.py` (accept an optional `checkpointer`)
- Modify: `founder-os/apps/api/app/main.py` (create the app-lifetime `AsyncPostgresSaver` in lifespan)
- Create: `founder-os/apps/api/alembic/versions/<rev>_langgraph_checkpoint_tables.py`
- Test: `founder-os/apps/api/tests/migrations/test_checkpoint_tables.py`

**Interfaces:**
- Produces: `build_graph(deps, checkpointer=None)` passes `checkpointer` to `.compile(checkpointer=checkpointer)`; a lifespan-managed `AsyncPostgresSaver` stored on `app.state.checkpointer` and threaded into `GraphDeps`/`OrchestratorAgent`.

- [ ] **Step 1: Write the failing migration test**

```python
# tests/migrations/test_checkpoint_tables.py
import pytest

pytestmark = pytest.mark.migrations

@pytest.mark.asyncio
async def test_checkpoint_tables_exist_after_upgrade(pg_engine):
    # pg_engine fixture points at the migrations test DB (see tests/migrations/conftest.py)
    async with pg_engine.connect() as conn:
        rows = await conn.exec_driver_sql(
            "SELECT tablename FROM pg_tables WHERE tablename LIKE 'checkpoint%'"
        )
        names = {r[0] for r in rows}
    assert "checkpoints" in names
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest -m migrations tests/migrations/test_checkpoint_tables.py -v`
Expected: FAIL — tables absent.

- [ ] **Step 3: Write the migration** (runs the checkpointer's own setup DDL)

```python
# alembic/versions/<rev>_langgraph_checkpoint_tables.py
"""langgraph checkpoint tables"""
from alembic import op
from langgraph.checkpoint.postgres import PostgresSaver  # sync saver for migration
from app.config import get_settings

revision = "<rev>"
down_revision = "<prev_head>"  # set via: alembic heads

def upgrade():
    dsn = get_settings().DATABASE_URL.replace("+asyncpg", "")
    with PostgresSaver.from_conn_string(dsn) as saver:
        saver.setup()

def downgrade():
    for tbl in ("checkpoint_blobs", "checkpoint_writes", "checkpoints", "checkpoint_migrations"):
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
```

Wire the async saver in `app/main.py` lifespan:
```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
# inside lifespan:
async with AsyncPostgresSaver.from_conn_string(get_settings().DATABASE_URL.replace("+asyncpg","")) as cp:
    app.state.checkpointer = cp
    yield
```
And thread `app.state.checkpointer` into the orchestrator (via registry `get(...)` kwargs → `OrchestratorAgent` → `build_graph(deps, checkpointer=...)`).

- [ ] **Step 4: Run to verify it passes**

Run: `alembic upgrade head && pytest -m migrations tests/migrations/test_checkpoint_tables.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/agents/graph/orchestrator_graph.py app/main.py alembic/versions/ tests/migrations/test_checkpoint_tables.py
git commit -m "feat(graph): AsyncPostgresSaver checkpointer + Alembic setup migration"
```

---

### Task 10: `/orchestrate/resume` endpoint (human-in-the-loop)

**Files:**
- Modify: `founder-os/apps/api/app/api/agent_routes.py`
- Test: `founder-os/apps/api/tests/regression/test_orchestrate_resume.py`

**Interfaces:**
- Consumes: the app checkpointer + `build_graph`.
- Produces: `POST /agents/orchestrate/resume` taking `{session_id, answer}`; re-invokes the graph with `Command(resume=answer)` on the same `thread_id`, returning the completed `OrchestrationResponse`.

- [ ] **Step 1: Write the failing test** (uses the test-user auth bypass, mocks the graph invoke)

```python
# tests/regression/test_orchestrate_resume.py
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_resume_requires_session_and_answer():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/agents/orchestrate/resume",
                          json={"session_id": ""}, headers={"x-test-user": "u1"})
    assert r.status_code == 422 or r.status_code == 400
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/regression/test_orchestrate_resume.py -v`
Expected: FAIL — route 404.

- [ ] **Step 3: Implement the endpoint** (mirror the `/orchestrate` auth + registry setup, then):

```python
from langgraph.types import Command

@router.post("/orchestrate/resume", response_model=OrchestrationResponse)
async def orchestrate_resume(body: ResumeRequest, user=Depends(require_auth), db=Depends(get_db)):
    if not body.session_id or body.answer is None:
        raise HTTPException(400, "session_id and answer are required")
    # build the orchestrator via registry (same as /orchestrate), then:
    deps = GraphDeps.from_agent(agent, ...)
    graph = build_graph(deps, checkpointer=request.app.state.checkpointer)
    final = await graph.ainvoke(Command(resume=body.answer),
                                config={"configurable": {"thread_id": body.session_id}})
    return _to_orchestration_response(final)
```
Add a `ResumeRequest` Pydantic model (`session_id: str`, `answer: str`).

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/regression/test_orchestrate_resume.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/agent_routes.py tests/regression/test_orchestrate_resume.py
git commit -m "feat(api): /orchestrate/resume for durable human-in-the-loop"
```

---

### Task 11: Parity + durability test suite (the safety net)

**Files:**
- Create: `founder-os/apps/api/tests/live/test_graph_parity.py` (marked `live` — needs stack + Ollama)
- Create: `founder-os/apps/api/tests/unit/test_graph_durability.py` (checkpointer via in-memory saver where possible)

**Interfaces:**
- Consumes: `build_graph`, a `MemorySaver` (from `langgraph.checkpoint.memory`) for durability unit tests.

- [ ] **Step 1: Write durability tests (unit, in-memory saver)**

```python
# tests/unit/test_graph_durability.py
import pytest
from langgraph.checkpoint.memory import MemorySaver
from app.agents.graph.orchestrator_graph import build_graph
from app.agents.graph.state import new_state

@pytest.mark.asyncio
async def test_completed_specialist_not_rerun_on_resume(monkeypatch):
    # deps whose fanout counts calls; interrupt before synthesize; resume; assert
    # the specialist ran exactly once across the two invocations.
    ...  # build deps with a call-counting router + needs_approval=True classify
    saver = MemorySaver()
    graph = build_graph(deps, checkpointer=saver)
    cfg = {"configurable": {"thread_id": "t1"}}
    await graph.ainvoke(new_state("u", "t1", "do X"), config=cfg)   # pauses at approval
    from langgraph.types import Command
    await graph.ainvoke(Command(resume="approved"), config=cfg)     # resumes
    assert deps.router.calls.count("planner") == 1
```

Fill the `...` with the call-counting fakes from Task 5's test (reuse `_FakeRouter`), and a classify fake returning `needs_approval=True, agents=["planner"]`.

- [ ] **Step 2: Run to verify it fails, then passes after wiring**

Run: `pytest tests/unit/test_graph_durability.py -v`
Expected: FAIL first (assertion / wiring), then PASS once the fakes are complete.

- [ ] **Step 3: Write the live parity test** (skipped unless `-m live`)

```python
# tests/live/test_graph_parity.py
import pytest
pytestmark = pytest.mark.live

PARITY_CASES = [
    ("What's the capital of France?", "SIMPLE", []),
    ("Research competitors then draft a launch plan", "MULTI_STEP", {"research", "planner"}),
    # ... ~8 more spanning simple / multi-step / complex / approval
]

@pytest.mark.asyncio
@pytest.mark.parametrize("msg,intent,agents", PARITY_CASES)
async def test_graph_selects_expected_agents(orchestrator_agent, msg, intent, agents):
    result = await orchestrator_agent.run(msg)
    used = {d.to_agent for d in result.delegations}
    if agents:
        assert used & set(agents)
    assert result.content  # coherent, non-empty
```

- [ ] **Step 4: Run the unit tier**

Run: `pytest tests/unit -k graph -v` then full `pytest`
Expected: all PASS. Live tier runs in CI/EC2.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_graph_durability.py tests/live/test_graph_parity.py
git commit -m "test(graph): durability + live parity suite"
```

---

### Task 12: Docs — ADR, DEPLOY note, roadmap, README

**Files:**
- Modify: `docs/decisions.md` (new ADR)
- Modify: `DEPLOY.md` (psycopg3 checkpointer DSN + resume endpoint)
- Modify: `docs/roadmap.md`
- Modify: `CLAUDE.md` §3 repo map (`app/agents/graph/`)

- [ ] **Step 1: Add the ADR** to `docs/decisions.md`:
  "ADR-0xx: Durable orchestration via LangGraph StateGraph" — context (3 limits), decision (thin-core graph, no LangChain models, in-place), consequences (new deps, psycopg3, checkpoint tables via Alembic), alternatives (full migration, DIY checkpointing) rejected.

- [ ] **Step 2: DEPLOY.md** — document the checkpointer DSN derivation, that `alembic upgrade head` creates the `checkpoint*` tables, and the new `/orchestrate/resume` endpoint.

- [ ] **Step 3: roadmap.md** — mark durable orchestrator shipped under §Now; **CLAUDE.md §3** — add `app/agents/graph/` to the repo map.

- [ ] **Step 4: Run docs sanity** — `grep -r "app/agents/graph" docs CLAUDE.md` shows the new references.

- [ ] **Step 5: Commit**

```bash
git add docs/decisions.md DEPLOY.md docs/roadmap.md CLAUDE.md
git commit -m "docs: ADR + deploy/roadmap for the LangGraph durable orchestrator"
```

---

## Final verification (before opening the PR)

- [ ] `cd founder-os/apps/api && source .venv/bin/activate && pytest` — unit + non-live regression green.
- [ ] `pytest -m migrations` — checkpoint-table migration green (needs a pgvector Postgres).
- [ ] `cd founder-os && turbo lint check-types build` — frontend untouched but keep `ci-success` honest.
- [ ] Confirm the SSE event contract by diffing emitted event types against the legacy set (parity test).
- [ ] Open PR to `main`; do NOT merge until `ci-success` is green and the live parity tier has been run in CI/EC2.

## Self-Review (completed by planner)

- **Spec coverage:** §3 architecture → Tasks 1,3,4,5,7,8; §4 state → Task 1; §5 nodes/edges → Tasks 3,4,5,6; §6 durability + stale-context → Tasks 6,9,11; §7 event contract → Task 5 + final verify; §8 testing → Tasks 11 + final; §9 risks (psycopg3, in-place) → Tasks 0,9,11; §10 success criteria → Task 11 parity. No uncovered sections.
- **Placeholder scan:** the only intentional `...` blocks are in Task 11 durability-test fakes, with explicit instructions to reuse Task 5's `_FakeRouter` + a `needs_approval=True` classify fake — actionable, not vague.
- **Type consistency:** `GraphDeps` exposes `llm, router, event_bus, memory, user_id, session_id, cheap_model, main_model, snapshot(), hydrate()` — used identically across Tasks 3,5,6,7,8. `make_*_node` / `build_graph(deps, checkpointer=None)` signatures match between definition and callers. `new_state(...)` signature matches every call site.
