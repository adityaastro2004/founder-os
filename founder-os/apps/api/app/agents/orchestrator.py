"""
Founder OS — Orchestrator Agent (durable graph)
================================================
The orchestrator runs as a durable LangGraph ``StateGraph`` (ADR-017). Its
``run()`` builds and invokes the graph defined in ``app/agents/graph/`` instead of
an LLM tool-loop; this class is now a thin adapter that owns the graph's
collaborators (router, memory, llm, event bus) and maps the graph's final state
back to an ``AgentResult``.

Flow (see ``app/agents/graph/orchestrator_graph.py``):

  classify ──cheap LLM──▶ {intent, planned_agents, needs_approval}
     │  conditional edges (0 tokens)
     ▼
  fanout ──▶ Planner / Content / Research / Support   (via the A2A router)
     │
     ▼
  approval? ──interrupt()──▶ [pause, checkpoint, resume via /orchestrate/resume]
     │
     ▼
  hydrate_context ──▶ synthesize ──main LLM──▶ final answer

Key properties:
  - Durable: an AsyncPostgresSaver checkpoints every node, so a run survives a
    restart and resumes without re-running completed specialists.
  - Cheap routing: one cheap-tier classify call + zero-token deterministic edges
    replace the old per-round LLM routing tool-calls.
  - Context-correct on resume: hydrate_context refreshes volatile company/task
    state before synthesis.
  - Unchanged below the node: specialists, tools, memory, event bus, and the
    3-tier provider fallback are reused as-is (no LangChain models).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from app.agents.base import BaseAgent, AgentConfig, AgentResult
from app.agents.event_bus import Event, EventBus
from app.agents.llm import LLMProvider
from app.agents.memory import AgentMemory
from app.agents.router import AgentRouter, DelegationResult
from app.agents.strategy import strategic_header
from app.agents.tool_protocol import ToolRegistry

logger = logging.getLogger(__name__)


# ============================================================================
# Delegation tracking (enhanced)
# ============================================================================

@dataclass
class DelegationStep:
    """Tracks a single delegation from orchestrator → specialist."""
    target_agent: str
    task: str
    result: str = ""
    success: bool = False
    tokens_used: int = 0
    duration_seconds: float = 0.0
    error: str = ""
    attempt: int = 1
    context_sent: str = ""


@dataclass
class OrchestrationTrace:
    """Full trace of an orchestration run."""
    delegations: list[DelegationStep] = field(default_factory=list)
    total_delegations: int = 0
    total_agent_tokens: int = 0
    agents_used: list[str] = field(default_factory=list)
    phases_completed: list[str] = field(default_factory=list)
    user_profile_loaded: bool = False
    memory_context_loaded: bool = False
    plan_created: bool = False
    actions_executed: list[str] = field(default_factory=list)
    retries: int = 0


# ============================================================================
# Orchestrator Agent
# ============================================================================

class OrchestratorAgent(BaseAgent):
    """
    The top-level manager agent, running as a durable LangGraph StateGraph (ADR-017).

    ``run()`` builds and invokes the graph in ``app/agents/graph/`` rather than an
    LLM tool-loop. The orchestrator itself has NO domain expertise: it classifies
    the request, routes to specialists via the A2A router, and synthesizes one
    coherent result — with durability (checkpointed) and human-in-the-loop
    (interrupt/resume) provided by the graph. This class owns the graph's
    collaborators and maps the final graph state back to an ``AgentResult``.
    """

    name = "orchestrator"
    capabilities = [
        "orchestration",
        "task_decomposition",
        "delegation",
        "synthesis",
        "multi_agent_coordination",
        "action_execution",
        "context_management",
    ]
    tags = [
        "manage", "coordinate", "help", "do", "handle",
        "figure out", "take care of", "assist", "run",
    ]

    # The orchestrator runs as a durable graph (ADR-017), not an LLM tool-loop:
    # its nodes call the A2A router directly and never expose tools to the LLM.
    # The classify/synthesize prompts live in app/agents/graph/nodes.py. These two
    # class attributes are kept only as agent-definition metadata (the router card
    # description + the DB agent sync); they are NOT used at orchestration runtime.
    default_tools: list[str] = []

    default_system_prompt = strategic_header(
        "Chief of Staff & Orchestrator",
        "You decompose requests, delegate precisely, propagate the founder's goal and "
        "constraints into every specialist brief, and synthesize one coherent result.",
    ) + (
        "You are the **Orchestrator** — Founder OS's chief of staff. You classify each "
        "request, route it to the right specialist(s) (planner, content, research, "
        "support), and synthesize one coherent, actionable result for the founder."
    )

    def __init__(
        self,
        config: AgentConfig,
        memory: AgentMemory,
        llm: LLMProvider,
        tools: ToolRegistry,
        router: AgentRouter | None = None,
        event_bus: EventBus | None = None,
        approval_gate: "Any | None" = None,
        user_id: str = "",
        embedder: "Any | None" = None,
    ) -> None:
        super().__init__(
            config, memory, llm, tools, router, event_bus,
            approval_gate, user_id, embedder,
        )
        self._trace = OrchestrationTrace()

    async def run(
        self,
        user_input: str,
        *,
        query_embedding: list[float] | None = None,
        extra_context: str | None = None,
    ) -> AgentResult:
        """
        Execute the orchestration as a durable LangGraph ``StateGraph``.

        Replaces the legacy LLM tool-loop (which decided delegations via a
        ``delegate_task`` tool) with an explicit graph:
        ``classify → route → specialists → (approval) → hydrate → synthesize``.
        The execution-engine loop is bypassed for the orchestrator only —
        specialists still run through their own ``base.run`` with full context.

        Everything ``base.run`` did that is NOT the tool loop is preserved here:
        the ``agent.started``-equivalent events, query auto-embedding, conversation
        persistence, and ``after_run`` (which stores ``last_orchestration``).
        """
        from app.agents.graph.deps import GraphDeps
        from app.agents.graph.orchestrator_graph import build_graph
        from app.agents.graph.state import new_state

        self._trace = OrchestrationTrace()
        start = time.time()

        # Emit orchestration.started with rich metadata
        if self.event_bus:
            await self.event_bus.publish(Event(
                type="orchestration.started",
                agent=self.name,
                data={
                    "input_preview": user_input[:300],
                    "input_length": len(user_input),
                    "phase": "starting",
                    "user_id": str(self.user_id),
                },
            ))

        # Record continuity (does a prior orchestration exist?)
        try:
            self._trace.memory_context_loaded = bool(
                await self.memory.get_from_shared("last_orchestration")
            )
        except Exception as exc:
            logger.warning("Failed to load prior orchestration: %s", exc)

        # Auto-embed the query for on-demand recall (parity with base.run step 1b)
        if query_embedding is None and self._embedder is not None:
            try:
                query_embedding = await self._embedder.embed(user_input)
            except Exception as exc:
                logger.warning("Auto-embedding failed, skipping RAG: %s", exc)

        # Persist the user turn (parity with base.run step 3)
        self.memory.conversation.add_user(user_input)

        # Build the graph from this agent's collaborators and invoke it
        deps = GraphDeps.from_agent(
            self,
            cheap_model=None,               # provider default = the cheap local tier
            main_model=self.config.model,   # synthesis uses the configured model
        )
        from app.agents.graph.checkpointer import get_checkpointer

        checkpointer = getattr(self, "_graph_checkpointer", None) or get_checkpointer()
        graph = build_graph(deps, checkpointer=checkpointer)

        thread_id = self.session_id or str(self.user_id)
        config = {"configurable": {"thread_id": thread_id}} if checkpointer else None

        init = new_state(
            str(self.user_id),
            self.session_id,
            user_input,
            query_embedding=query_embedding,
            extra_context=extra_context or "",
        )
        final = await graph.ainvoke(init, config=config)

        result = self._result_from_state(final, start)

        # Persist the assistant turn (parity with base.run step 6)
        if result.content:
            self.memory.conversation.add_assistant(result.content)

        # Post-run hook — stores last_orchestration (parity with base.run step 8)
        await self.after_run(user_input, result)

        # Emit orchestration.completed with full trace
        if self.event_bus:
            await self.event_bus.publish(Event(
                type="orchestration.completed",
                agent=self.name,
                data={
                    "delegations": self._trace.total_delegations,
                    "agents_used": self._trace.agents_used,
                    "total_tokens": result.tokens_used,
                    "duration": result.duration_seconds,
                    "phases_completed": self._trace.phases_completed,
                    "retries": self._trace.retries,
                    "actions_executed": self._trace.actions_executed,
                    "profile_loaded": self._trace.user_profile_loaded,
                    "memory_loaded": self._trace.memory_context_loaded,
                    "user_id": str(self.user_id),
                },
            ))

        return result

    def _result_from_state(self, final: dict, start: float) -> AgentResult:
        """Map the final graph state → ``AgentResult`` and populate ``self._trace``.

        Preserves the delegation shape existing callers rely on
        (``result.delegations`` of ``DelegationResult``). If the graph paused at an
        approval interrupt, surfaces it via ``pending_approvals`` instead of a body.
        """
        duration = time.time() - start

        # An interrupted run (awaiting human approval) returns the interrupt payload
        interrupt = final.get("__interrupt__") if isinstance(final, dict) else None
        if interrupt:
            self._trace.phases_completed.append("interrupted:approval")
            return AgentResult(
                content="",
                duration_seconds=duration,
                pending_approvals=[{"reason": "approval_required",
                                    "session_id": self.session_id}],
            )

        trace_entries = final.get("trace", []) or []
        total_tokens = sum(int(t.get("tokens_used", 0) or 0) for t in trace_entries)

        delegations: list[DelegationResult] = []
        for entry in trace_entries:
            agent_name = entry.get("agent")
            if not agent_name:
                continue  # classify / synthesize bookkeeping rows
            success = bool(entry.get("success"))
            delegations.append(DelegationResult(
                from_agent="orchestrator",
                to_agent=agent_name,
                task="",
                success=success,
                content=(final.get("results", {}).get(agent_name, "") or "")[:500],
                error=entry.get("error", "") or "",
                tokens_used=int(entry.get("tokens_used", 0) or 0),
            ))
            if success and agent_name not in self._trace.agents_used:
                self._trace.agents_used.append(agent_name)
            self._trace.phases_completed.append(f"delegation:{agent_name}")

        self._trace.total_delegations = len(delegations)
        self._trace.total_agent_tokens = total_tokens

        return AgentResult(
            content=final.get("final_answer", "") or "",
            tokens_used=total_tokens,
            duration_seconds=duration,
            model=self.config.model,
            delegations=delegations,
        )

    # NOTE: no before_run — current_plan and research_findings already render
    # via <shared_memory>; copying them into working memory doubled the tokens.

    async def after_run(self, user_input: str, result: AgentResult) -> None:
        """Persist orchestration trace for continuity and analysis."""
        if not result.content:
            return

        summary = {
            "user_request": user_input[:500],
            "agents_used": self._trace.agents_used,
            "delegations": self._trace.total_delegations,
            "summary": result.content[:1500],
            "actions_taken": self._trace.actions_executed,
            "tokens_total": result.tokens_used + self._trace.total_agent_tokens,
            "profile_loaded": self._trace.user_profile_loaded,
        }

        delegation_details = []
        for d in self._trace.delegations:
            delegation_details.append({
                "agent": d.target_agent,
                "task_summary": d.task[:200],
                "success": d.success,
                "result_preview": d.result[:300] if d.result else "",
            })
        summary["delegation_details"] = delegation_details

        await self.memory.save_to_shared(
            "last_orchestration",
            json.dumps(summary, default=str),
        )

        await self.memory.save_to_shared(
            "last_agents_used",
            json.dumps(self._trace.agents_used),
        )

    # ------------------------------------------------------------------
    # Workflow generation (Wave 2b / ADR-008 US-1) — additive, off the main loop
    # ------------------------------------------------------------------

    async def generate_and_persist_workflow(
        self,
        db: "Any",
        goal: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        context: Optional[str] = None,
    ) -> "Any":
        """
        Auto-generate a workflow IR from a founder's natural-language goal and
        persist it as a `Workflow` owned by this orchestrator's user.

        Thin, additive entry point (does NOT alter the orchestration loop). It
        reuses the orchestrator's own provider-neutral LLM (`self.llm`) and bound
        `user_id`, generates a validated IR via `app.workflows.generator`, and
        persists it via `app.workflows.service.create_workflow`. `n8n_workflow_id`
        is left NULL — compile+push to n8n is Wave 3.

        Wave 3 should call THIS method from the workflow API/orchestrate path when
        a founder asks to automate/schedule a recurring goal, then compile the
        returned workflow's `steps` IR and push it to n8n, recording the returned
        n8n id via `service.set_n8n_workflow_id`.

        Raises `WorkflowGenerationError` (from the generator) if no valid IR could
        be produced — never persists an invalid IR (O-1-AMEND / C-8).
        """
        from app.workflows.generator import generate_workflow_ir
        from app.workflows.ir import parse_ir
        from app.workflows.service import create_workflow

        ir = await generate_workflow_ir(self.llm, goal, context=context)

        # `generate_workflow_ir` already ran validate_ir; this normalises the
        # stored shape and would surface any residual schema drift loudly.
        parsed = parse_ir(ir)
        is_scheduled = parsed.trigger.type == "cron"
        schedule_cron = getattr(parsed.trigger, "cron", None)

        workflow = await create_workflow(
            db,
            user_id=str(self.user_id),
            name=name or (goal.strip()[:120] or "Untitled workflow"),
            description=description or goal.strip()[:500],
            steps=ir,
            is_scheduled=is_scheduled,
            schedule_cron=schedule_cron,
            n8n_workflow_id=None,  # Wave 3: set after compile + push to n8n
        )
        logger.info(
            "generate_and_persist_workflow: persisted workflow %s for user %s (%d steps, scheduled=%s)",
            workflow.id, self.user_id, len(parsed.steps), is_scheduled,
        )
        return workflow
