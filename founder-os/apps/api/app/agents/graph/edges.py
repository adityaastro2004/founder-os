"""Deterministic routing edges for the orchestrator graph.

These are plain functions over the state — they cost **zero tokens**. This is the
core of "routing through logic and state": the expensive LLM decision happens once
in ``classify``; everything after is deterministic dispatch.
"""

from __future__ import annotations


def route_after_classify(state) -> str:
    """Pick the next node after classification.

    - ``COMPLEX`` intent → ``llm_route`` (full LLM routing escape hatch)
    - any planned agents → ``fanout`` (run specialists)
    - otherwise → ``synthesize`` (answer directly)
    """
    if state["intent"] == "COMPLEX":
        return "llm_route"
    if state["planned_agents"]:
        return "fanout"
    return "synthesize"


def pending_agents(state) -> list[str]:
    """Planned agents not yet present in ``results`` (drives sequential execution
    and makes resume cheap — completed specialists are skipped)."""
    done = set(state["results"])
    return [a for a in state["planned_agents"] if a not in done]
