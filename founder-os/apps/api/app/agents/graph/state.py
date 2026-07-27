"""Orchestrator graph state.

`OrchestratorState` is the typed value that flows through the graph and — with a
checkpointer attached — is what LangGraph persists after every node. `results`
accumulating across nodes is what makes crash-resume cheap: a completed
specialist's output lives in the checkpoint, so a resumed run never re-runs or
re-pays for it.

The context surface mirrors what `base.py` injects at run time (profile, company
business context, task/shared memory, cross-session recall) — routing and
synthesis must see the company and its current work, not the founder profile alone.
"""

from __future__ import annotations

from typing import TypedDict


class OrchestratorState(TypedDict):
    user_id: str
    session_id: str
    user_input: str
    query_embedding: list[float] | None  # reused for on-demand recall mid-graph

    # ── context surface (mirrors base.py injection) ──
    profile_context: str    # founder profile
    company_context: str    # <founder_business_context> + State Engine snapshot
    task_context: str       # current_plan, last_orchestration, research_findings
    memory_context: str     # <memories> cross-session semantic recall
    extra_context: str      # passthrough from the API (extra_context param)

    # ── working state — accumulates across nodes so resume never re-pays ──
    intent: str             # SIMPLE | MULTI_STEP | COMPLEX
    planned_agents: list[str]
    results: dict[str, str]  # agent_name -> output; checkpointed, never re-run
    needs_approval: bool
    approval_answer: str | None  # filled on resume
    final_answer: str
    trace: list[dict]       # feeds the event bus + OrchestrationTrace parity


def new_state(
    user_id: str,
    session_id: str,
    user_input: str,
    *,
    query_embedding: list[float] | None = None,
    extra_context: str = "",
) -> OrchestratorState:
    """Build the initial graph state for a fresh orchestration run."""
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
