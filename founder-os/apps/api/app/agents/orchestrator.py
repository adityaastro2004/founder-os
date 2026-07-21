"""
Founder OS — Orchestrator Agent (v3)
======================================
Stripe Minions-inspired intelligent orchestration layer.

The orchestrator is the **single brain** that:
  1. Deeply understands user intent (pre-analysis)
  2. Decomposes complex requests into an execution plan
  3. Enriches each sub-task with full context before delegation
  4. Delegates to specialists (parallel when independent)
  5. Validates specialist outputs (retries on failure)
  6. Synthesises results into coherent, actionable responses
  7. Executes actions in connected apps when appropriate

Architecture:

  ┌─────────────────────────────────────────────────────────┐
  │                     User Message                         │
  └────────────────────────┬────────────────────────────────┘
                           ▼
  ┌─────────────────────────────────────────────────────────┐
  │                   ORCHESTRATOR v3                        │
  │                                                         │
  │  Phase 1: UNDERSTAND                                    │
  │    → Analyse intent, load user profile & memory         │
  │    → Classify complexity (simple / multi-step / complex)│
  │    → Identify required specialists & dependencies       │
  │                                                         │
  │  Phase 2: PLAN                                          │
  │    → Decompose into ordered sub-tasks                   │
  │    → Determine parallel vs sequential execution         │
  │    → Enrich each task with full context                 │
  │                                                         │
  │  Phase 3: DELEGATE                                      │
  │    → Send enriched tasks to specialists                 │
  │    → Monitor progress via event bus                     │
  │    → Validate outputs, retry on failure                 │
  │                                                         │
  │  Phase 4: SYNTHESISE                                    │
  │    → Combine specialist outputs intelligently           │
  │    → Execute actions in connected apps if needed        │
  │    → Present coherent response to user                  │
  │                                                         │
  └───────┬──────────┬──────────┬──────────┬───────────────┘
          ▼          ▼          ▼          ▼
      ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
      │Planner │ │Content │ │Research│ │  Ops   │  ...
      │ Agent  │ │ Agent  │ │ Agent  │ │ Agent  │
      └────────┘ └────────┘ └────────┘ └────────┘

Key principles:
  - Agents-as-tools: each specialist is exposed to the LLM as a callable tool
  - The orchestrator's LLM decides the routing — no hardcoded if/else
  - The orchestrator UNDERSTANDS specialist outputs, doesn't just relay them
  - Cross-agent memory sharing for context continuity
  - Full trace: every phase is logged and visible
  - Graceful fallback: simple questions answered directly
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from app.agents.base import BaseAgent, AgentConfig, AgentResult
from app.agents.event_bus import Event, EventBus
from app.agents.execution import ExecutionEngine, ExecutionResult
from app.agents.llm import LLMMessage, LLMProvider, Role, ToolSchema
from app.agents.memory import AgentMemory
from app.agents.router import AgentCard, AgentRouter, DelegationResult
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
    The top-level manager agent (Stripe Minions pattern, v3).

    Unlike other agents that handle domain-specific tasks, the orchestrator:
    - Deeply analyses ANY user request before acting
    - Plans an execution strategy with dependency awareness
    - Enriches each delegation with full context (profile, memory, prior results)
    - Validates specialist outputs and retries on failure
    - Synthesises intelligently — not just concatenating outputs
    - Executes actions in connected apps when agents produce actionable outputs

    The orchestrator has NO domain expertise of its own. Its skill is
    *knowing who knows what*, *combining their outputs intelligently*,
    and *taking action on behalf of the user*.
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

    # Prompt already contains the specialist table — skip the injected
    # <available_agents> block that would duplicate it.
    inject_delegation_context = False

    # Tools available to the orchestrator LLM
    default_tools = [
        "delegate_task",
        "get_current_datetime",
        "get_user_profile",
        "ask_user_clarification",
        "store_working_memory",
        "search_knowledge",
        "recall_last_orchestration",
        "list_available_agents",
        "check_delegation_health",
    ]

    default_system_prompt = strategic_header(
        "Chief of Staff & Orchestrator",
        "You decompose requests, delegate precisely, propagate the founder's goal and "
        "constraints into every specialist brief, and synthesize one coherent result.",
    ) + """\
You are the **Orchestrator** — Founder OS's chief of staff. You think strategically, \
delegate precisely, and deliver results.

## PROTOCOL — every request

**1. UNDERSTAND** — the founder's profile, business context, prior conversation, \
and last orchestration are already injected above — use them directly (call \
`get_user_profile` / `recall_last_orchestration` only if something you need is \
missing). Classify: SIMPLE (handle directly / single delegation), MULTI-STEP \
(2-3 agents in sequence), or COMPLEX (clarify first via `ask_user_clarification`).

**2. PLAN** — decompose into sub-tasks. For each, decide: which specialist, what \
order (research → planning → content), what context to include (goal, stage, \
timezone, prior results).

**3. DELEGATE** — call `delegate_task` with a *rewritten* instruction (never the \
raw user message), the right `agent_name`, and enriched `context`. Validate each \
output — re-delegate if incomplete. Chain results: include Task A's output in \
Task B's context.

**4. SYNTHESISE** — lead with the answer, weave specialist insights naturally \
(say "Market analysis shows…" not "The research agent found…"), list actions \
taken with ✅, end with 2-3 **Next Steps**.

## SPECIALIST AGENTS (the only valid `agent_name` values)

| Agent | Best for | Key access | Include in context |
|-------|----------|------------|-------------------|
| **planner** | Planning, scheduling, calendar, tasks, OKRs | Google Calendar, tasks, ICE scoring | Goal, timezone, schedule |
| **content** | Blog, social, email, newsletters, copy, PRDs, specs | Writing style, KB, drafts | Voice, audience, platform |
| **research** | Market research, competitors, trends, metrics, integrations | Web search, KB, metrics, integrations | Industry, competitors, questions |
| **support** | Customer emails, FAQs, playbooks | KB, tasks | Customer context, tone |

## CRITICAL RULES
1. Use the injected profile context in every delegation — never delegate without it
2. NEVER forward raw user message — always rewrite as specialist instruction
3. NEVER ignore specialist errors — retry with more context or explain to user
4. ALWAYS include founder's primary goal + timezone in planning delegations
5. ALWAYS validate specialist outputs are complete and actionable
6. Confirm DESTRUCTIVE operations (deletions) before executing
7. Default to planner if unsure which agent
"""

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
        Execute the full orchestration loop.

        The LLM follows the 4-phase protocol:
        UNDERSTAND → PLAN → DELEGATE → SYNTHESISE.
        """
        self._trace = OrchestrationTrace()

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

        # Continuity context: last_orchestration lives in shared memory and
        # already renders in <shared_memory> — copying it into working memory
        # duplicated it in the same prompt. Just record whether it exists.
        try:
            self._trace.memory_context_loaded = bool(
                await self.memory.get_from_shared("last_orchestration")
            )
        except Exception as exc:
            logger.warning("Failed to load prior orchestration: %s", exc)

        # Run the LLM loop — tools guide the 4-phase protocol
        result = await super().run(
            user_input,
            query_embedding=query_embedding,
            extra_context=extra_context,
        )

        # Enrich result with orchestration metadata
        result.delegations = [
            DelegationResult(
                from_agent="orchestrator",
                to_agent=d.target_agent,
                task=d.task,
                success=d.success,
                content=d.result[:500] if d.result else "",
                error=d.error,
                tokens_used=d.tokens_used,
                duration_seconds=d.duration_seconds,
            )
            for d in self._trace.delegations
        ]

        # Emit orchestration.completed with full trace
        if self.event_bus:
            await self.event_bus.publish(Event(
                type="orchestration.completed",
                agent=self.name,
                data={
                    "delegations": self._trace.total_delegations,
                    "agents_used": self._trace.agents_used,
                    "total_tokens": result.tokens_used + self._trace.total_agent_tokens,
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

    # ------------------------------------------------------------------
    # Delegation execution (called by the delegate_task tool)
    # ------------------------------------------------------------------

    async def execute_delegation(
        self,
        agent_name: str,
        task: str,
        context: str = "",
        *,
        user_id: Any = None,
        session_id: str | None = None,
        max_retries: int = 1,
    ) -> str:
        """
        Run a specialist agent with full context enrichment.

        Enhanced with:
        - Pre-delegation event emission for UI streaming
        - Context enrichment
        - Output validation
        - Retry on failure
        - Post-delegation result caching
        """
        start = time.time()
        attempt = 0

        if self.event_bus:
            await self.event_bus.publish(Event(
                type="delegation.starting",
                agent=self.name,
                data={
                    "target_agent": agent_name,
                    "task_preview": task[:200],
                    "has_context": bool(context),
                    "user_id": str(user_id if user_id is not None else self.user_id),
                },
            ))

        while attempt <= max_retries:
            attempt += 1
            step = DelegationStep(
                target_agent=agent_name,
                task=task,
                attempt=attempt,
                context_sent=context[:500] if context else "",
            )

            try:
                delegation_input = self._build_delegation_input(
                    task, context, attempt,
                )

                if not self.router:
                    step.error = "No router configured — cannot delegate"
                    step.success = False
                    self._trace.delegations.append(step)
                    return json.dumps({"error": step.error})

                from app.agents.router import AgentMessage

                message = AgentMessage(
                    from_agent="orchestrator",
                    to_agent=agent_name,
                    task=delegation_input,
                    context={
                        "orchestrated": True,
                        "attempt": attempt,
                        "has_profile_context": self._trace.user_profile_loaded,
                    },
                )

                if self.event_bus:
                    await self.event_bus.publish(Event(
                        type="delegation.executing",
                        agent=agent_name,
                        data={
                            "from": "orchestrator",
                            "task_preview": task[:150],
                            "attempt": attempt,
                            "user_id": str(user_id if user_id is not None else self.user_id),
                        },
                    ))

                delegation_result = await self.router.delegate(
                    message,
                    user_id=user_id,
                    session_id=session_id,
                )

                duration = time.time() - start
                step.duration_seconds = duration
                step.tokens_used = delegation_result.tokens_used
                step.success = delegation_result.success

                if delegation_result.success:
                    step.result = delegation_result.content
                    self._trace.total_agent_tokens += delegation_result.tokens_used
                    if agent_name not in self._trace.agents_used:
                        self._trace.agents_used.append(agent_name)

                    # Cache output in shared memory for cross-agent use
                    try:
                        await self.memory.save_to_shared(
                            f"last_{agent_name}_output",
                            delegation_result.content[:2000],
                        )
                    except Exception:
                        pass

                    if self.event_bus:
                        await self.event_bus.publish(Event(
                            type="delegation.completed",
                            agent=agent_name,
                            data={
                                "from": "orchestrator",
                                "success": True,
                                "tokens_used": delegation_result.tokens_used,
                                "duration": round(duration, 2),
                                "result_preview": delegation_result.content[:200],
                                "user_id": str(user_id if user_id is not None else self.user_id),
                            },
                        ))

                    self._trace.delegations.append(step)
                    self._trace.total_delegations += 1
                    self._trace.phases_completed.append(
                        f"delegation:{agent_name}"
                    )

                    return json.dumps({
                        "agent": agent_name,
                        "status": "success",
                        "response": step.result,
                        "tokens_used": step.tokens_used,
                        "duration_seconds": round(step.duration_seconds, 2),
                    })

                else:
                    step.error = delegation_result.error or "Delegation failed"
                    logger.warning(
                        "Delegation to '%s' failed (attempt %d/%d): %s",
                        agent_name, attempt, max_retries + 1, step.error,
                    )

                    if attempt <= max_retries:
                        self._trace.retries += 1
                        if self.event_bus:
                            await self.event_bus.publish(Event(
                                type="delegation.retrying",
                                agent=agent_name,
                                data={
                                    "attempt": attempt + 1,
                                    "reason": step.error[:200],
                                    "user_id": str(user_id if user_id is not None else self.user_id),
                                },
                            ))
                        continue

            except Exception as exc:
                step.error = str(exc)
                step.success = False
                logger.exception(
                    "Delegation to '%s' failed (attempt %d)",
                    agent_name, attempt,
                )
                if attempt <= max_retries:
                    self._trace.retries += 1
                    continue

            # All retries exhausted
            self._trace.delegations.append(step)
            self._trace.total_delegations += 1

            if self.event_bus:
                await self.event_bus.publish(Event(
                    type="delegation.failed",
                    agent=agent_name,
                    data={
                        "from": "orchestrator",
                        "error": step.error[:300],
                        "attempts": attempt,
                        "user_id": str(user_id if user_id is not None else self.user_id),
                    },
                ))

            return json.dumps({
                "agent": agent_name,
                "status": "error",
                "error": step.error,
                "attempts": attempt,
                "suggestion": self._get_fallback_suggestion(agent_name, step.error),
            })

        return json.dumps({
            "agent": agent_name,
            "status": "error",
            "error": "Exhausted all retry attempts",
        })

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_delegation_input(
        self,
        task: str,
        context: str,
        attempt: int,
    ) -> str:
        """Build enriched input for a specialist."""
        parts = [task]

        if context:
            parts.append(
                f"\n\n<orchestrator_context>\n{context}\n</orchestrator_context>"
            )

        if attempt > 1:
            parts.append(
                "\n\n<retry_note>This is a retry. The previous attempt "
                "failed or returned incomplete results. Please try a "
                "different approach or be more thorough.</retry_note>"
            )

        return "\n".join(parts)

    @staticmethod
    def _get_fallback_suggestion(agent_name: str, error: str) -> str:
        """Suggest recovery actions when a delegation fails."""
        error_lower = error.lower()

        if "not found" in error_lower or "inactive" in error_lower:
            return (
                f"Agent '{agent_name}' is not available. "
                "Try using 'planner' as a fallback, or handle directly."
            )
        if "timeout" in error_lower:
            return (
                f"Agent '{agent_name}' timed out. "
                "Try breaking the task into smaller sub-tasks."
            )
        if "rate_limit" in error_lower or "429" in error_lower:
            return (
                "LLM rate limit hit. Wait a moment and try again, "
                "or simplify the request."
            )
        return (
            f"Delegation to '{agent_name}' failed. "
            "Try rephrasing the task with more specific instructions, "
            "or handle this part directly."
        )
