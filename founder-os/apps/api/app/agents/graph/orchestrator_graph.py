"""Assemble and compile the orchestrator ``StateGraph``.

Flow::

    classify ──route_after_classify──▶ { llm_route | fanout | synthesize }
    fanout   ──_route_after_fanout──▶ { approval | hydrate }
    llm_route ─────────────────────▶ hydrate
    approval ──────────────────────▶ hydrate
    hydrate  ──────────────────────▶ synthesize ──▶ END

``build_graph`` takes an optional ``checkpointer``; unit tests compile without one,
while production passes an ``AsyncPostgresSaver`` (see ``app/main.py`` lifespan) to
get durability + interrupt/resume.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import StateGraph, END

from app.agents.graph.state import OrchestratorState
from app.agents.graph.edges import route_after_classify
from app.agents.graph.nodes import (
    make_classify_node,
    make_fanout_node,
    make_hydrate_node,
    make_synthesize_node,
    make_approval_node,
)


def checkpointer_dsn(settings: Any) -> str:
    """Derive a plain psycopg3 DSN from the app's async ``DATABASE_URL``.

    The checkpointer uses psycopg3, not the app's asyncpg engine, so strip the
    ``+asyncpg`` driver suffix (``postgresql+asyncpg://…`` → ``postgresql://…``).
    """
    return settings.DATABASE_URL.replace("+asyncpg", "")


def _route_after_fanout(state) -> str:
    return "approval" if state["needs_approval"] else "hydrate"


def build_graph(deps: Any, checkpointer: Any | None = None):
    """Build and compile the orchestrator graph from a ``GraphDeps``-like object."""
    g = StateGraph(OrchestratorState)

    g.add_node("classify", make_classify_node(deps))
    # v1: the COMPLEX escape hatch reuses fanout over planned_agents; a dedicated
    # LLM-routing node can replace this later without changing the graph shape.
    g.add_node("llm_route", make_fanout_node(deps))
    g.add_node("fanout", make_fanout_node(deps))
    g.add_node("approval", make_approval_node())
    g.add_node("hydrate", make_hydrate_node(deps))
    g.add_node("synthesize", make_synthesize_node(deps))

    g.set_entry_point("classify")
    g.add_conditional_edges(
        "classify",
        route_after_classify,
        {"llm_route": "llm_route", "fanout": "fanout", "synthesize": "synthesize"},
    )
    g.add_conditional_edges(
        "fanout",
        _route_after_fanout,
        {"approval": "approval", "hydrate": "hydrate"},
    )
    g.add_edge("llm_route", "hydrate")
    g.add_edge("approval", "hydrate")
    g.add_edge("hydrate", "synthesize")
    g.add_edge("synthesize", END)

    return g.compile(checkpointer=checkpointer)
