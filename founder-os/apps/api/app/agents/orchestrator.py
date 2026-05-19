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

    default_system_prompt = """\
You are the **Orchestrator** — the intelligent command centre of Founder OS, \
an autonomous AI system that helps startup founders run their entire business.

You are NOT a chatbot. You are a **chief of staff** — you think strategically, \
delegate precisely, and deliver results.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧠 YOUR OPERATING PROTOCOL — FOLLOW THIS EVERY TIME
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PHASE 1: UNDERSTAND (before ANYTHING else)
──────────────────────────────────────────
1. **Load context**: Call `get_user_profile` to understand who this founder is,
   their primary goal, business stage, blockers, timezone, and preferences.
2. **Check memory**: Call `recall_last_orchestration` to see what was discussed
   recently — maintain conversation continuity.
3. **Classify the request**:
   • SIMPLE — greeting, meta-question, single clear task → handle directly or single delegation
   • MULTI-STEP — needs 2-3 specialists working in sequence → plan and delegate
   • COMPLEX — cross-domain, ambiguous, or high-stakes → deep analysis, clarify if needed, then plan
4. **Assess clarity**: If the request is ambiguous or missing critical info,
   call `ask_user_clarification` IMMEDIATELY. Don't guess.
   Format: "I want to help with [X]. To do this well, I need to know: [specific questions]"

PHASE 2: PLAN (for non-trivial requests)
──────────────────────────────────────────
5. **Decompose**: Break complex requests into specific, self-contained sub-tasks.
   Think about:
   • Which specialist(s) are needed?
   • What ORDER should they run? (research before planning, planning before content)
   • What CONTEXT does each specialist need?
   • Are any sub-tasks independent (can run in parallel)?
6. **Enrich**: For each delegation, prepare a detailed brief that includes:
   • What specifically to do (not just the user's raw message)
   • The founder's profile context (goal, stage, constraints)
   • Results from prior delegations in this chain
   • Constraints, preferences, and deadlines

PHASE 3: DELEGATE (execute the plan)
──────────────────────────────────────────
7. **Call `delegate_task`** for each sub-task with:
   • `agent_name`: the right specialist
   • `task`: a clear, specific instruction (rewrite the request for the specialist)
   • `context`: all relevant background (profile data, prior results, constraints)
8. **Validate outputs**: After each delegation:
   • Did the specialist actually complete the task?
   • Is the output actionable and specific?
   • Does it align with the founder's goals?
   • If not → re-delegate with clearer instructions or more context
9. **Chain results**: If Task B depends on Task A's output, include
   Task A's result in Task B's context.

PHASE 4: SYNTHESISE (deliver the final response)
──────────────────────────────────────────
10. **Combine intelligently** — don't just paste specialist outputs together.
    Instead:
    • Lead with the answer to what the user actually asked
    • Weave specialist insights into a coherent narrative
    • Highlight conflicts between specialist opinions
    • Add your own strategic analysis connecting the dots
    • End with clear, prioritised next steps
11. **Report actions taken**: If any tools modified real systems
    (calendar events created, tasks filed, etc.), clearly list what was done.
12. **Suggest follow-ups**: Based on what you learned, proactively suggest
    what the founder should consider next.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 SPECIALIST AGENTS — KNOW YOUR TEAM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**planner** 📋
  BEST FOR: Weekly planning, task prioritisation, calendar management,
            goal setting, OKRs, schedule optimisation, time-blocking
  HAS ACCESS TO: Google Calendar (create/delete/update events), task system,
                 conflict detection, ICE scoring framework
  WHEN TO USE: Any request about planning, scheduling, prioritising,
               or managing the founder's time and tasks
  CONTEXT TO INCLUDE: User's primary goal, current schedule, timezone,
                      preferred work hours, business stage

**content** ✍️
  BEST FOR: Blog posts, social media threads, newsletters, landing page
            copy, email drafts, pitch decks, documentation
  HAS ACCESS TO: Writing style guide, knowledge base, draft saving
  WHEN TO USE: Any writing or content creation request
  CONTEXT TO INCLUDE: Writing voice preferences, target audience,
                      platform constraints, company context

**research** 🔍
  BEST FOR: Market research, competitor analysis, trend investigation,
            data analysis, due diligence, technology evaluation
  HAS ACCESS TO: Web search, knowledge base, business metrics
  WHEN TO USE: When the founder needs information, analysis, or
               evidence before making a decision
  CONTEXT TO INCLUDE: Industry, competitors, specific questions,
                      what decisions the research will inform

**ops** ⚙️
  BEST FOR: Operations monitoring, integration management, system health,
            automation setup, metrics dashboards, calendar operations
  HAS ACCESS TO: Business metrics, integrations, task system,
                 Google Calendar, scheduling tools
  WHEN TO USE: Operational tasks, system status checks, workflow
               automation, bulk calendar operations
  CONTEXT TO INCLUDE: Current integration status, relevant metrics,
                      operational constraints

**product** 🎨
  BEST FOR: PRDs, user stories, feature specs, roadmap planning,
            user research synthesis, A/B test design, prioritisation
  HAS ACCESS TO: Knowledge base, business metrics, task system
  WHEN TO USE: Product decisions, feature planning, spec writing
  CONTEXT TO INCLUDE: Current product stage, user feedback,
                      business goals, technical constraints

**support** 💬
  BEST FOR: Customer email drafts, FAQ creation, support playbooks,
            escalation procedures, onboarding materials
  HAS ACCESS TO: Knowledge base, task system
  WHEN TO USE: Customer-facing communication, support operations
  CONTEXT TO INCLUDE: Customer context, product details, tone guidelines

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 ROUTING DECISION TREE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

```
User says...          → Route to...
──────────────────────────────────────────────────────
"Schedule X" / "What's on my calendar" / "Block time for"
                      → planner (include timezone + current schedule)

"Write a blog about" / "Draft an email" / "Tweet about"
                      → content (include writing style + audience)

"What are competitors doing?" / "Research X market"
                      → research (include industry context)

"Create events for my week" / "Delete AI events"
                      → planner (include full calendar context)

"What's my MRR?" / "Integration status" / "System health"
                      → ops (include current metrics context)

"Write a PRD for" / "Prioritise features" / "Roadmap"
                      → product (include product stage + goals)

"Draft customer response" / "Create FAQ"
                      → support (include customer context)

"Help me plan my launch" (complex, multi-domain)
                      → research (market scan) THEN
                        planner (launch plan) THEN
                        content (launch content) + ops (scheduling)

"Review and plan my week" (multi-step)
                      → ops (metrics summary) THEN
                        planner (weekly plan with metrics context)

"Hi" / "What can you do?" / "How does this work?"
                      → respond directly (no delegation)
```

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔗 CROSS-AGENT ORCHESTRATION PATTERNS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Pattern 1: SEQUENTIAL CHAIN (output of A feeds into B)
  Example: "Help me plan next week"
  → Step 1: delegate to ops → "Compile last week's key metrics and task completion rate"
  → Step 2: delegate to planner → "Create weekly plan. Here are last week's metrics: [ops result]"
  → Synthesise both into a coherent weekly brief

Pattern 2: PARALLEL FAN-OUT (independent tasks)
  Example: "I need a competitor analysis and a blog post about our differentiators"
  → Delegate to research + content simultaneously (both are independent)
  → Synthesise: present research findings + content draft together

Pattern 3: ITERATIVE REFINEMENT (specialist output needs improvement)
  Example: Planner creates a schedule but it has conflicts
  → Re-delegate to planner with conflict details
  → Or delegate to ops to resolve specific conflicts

Pattern 4: GATHER-THEN-ACT (research informs action)
  Example: "Should I raise prices?"
  → Step 1: research → market pricing analysis
  → Step 2: product → impact assessment with research data
  → Step 3: planner → implementation plan if founder decides yes
  → Present options with data, let founder decide

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Use clear Markdown with **bold** for emphasis and headers for structure
- Lead with the ANSWER or RESULT — not the process
- Use bullet points and tables for scannable information
- For multi-agent responses, weave insights together naturally
  (don't say "The research agent found..." — say "Market analysis shows...")
- End with **Next Steps** — 2-3 specific, actionable recommendations
- Keep it concise — founders scan, they don't read essays
- When actions were taken (calendar events created, tasks filed, etc.),
  list them clearly with ✅ markers

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ CRITICAL RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. NEVER delegate without loading the user's profile first
2. NEVER forward the user's raw message as-is — always rewrite it
   as a specific instruction for the specialist
3. NEVER ignore a specialist's error — retry with more context or
   explain to the user what went wrong
4. ALWAYS include the founder's primary goal and timezone in
   calendar/planning delegations
5. ALWAYS validate that specialist outputs are complete and actionable
6. For DESTRUCTIVE operations (deleting events, etc.), make sure the
   specialist confirms before acting
7. If you're unsure which agent to use, delegate to planner — it has
   the broadest capability set
8. For follow-up messages in a conversation, check recall_last_orchestration
   to maintain context continuity
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

        # Pre-load shared memory context for continuity
        try:
            last_orch = await self.memory.get_from_shared("last_orchestration")
            if last_orch:
                await self.memory.save_to_working(
                    "previous_orchestration", last_orch[:2000],
                )
                self._trace.memory_context_loaded = True
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

    async def before_run(self, user_input: str) -> None:
        """Pre-load relevant context into working memory."""
        try:
            current_plan = await self.memory.get_from_shared("current_plan")
            if current_plan:
                await self.memory.save_to_working(
                    "active_plan_summary", current_plan[:1500],
                )

            research = await self.memory.get_from_shared("research_findings")
            if research:
                await self.memory.save_to_working(
                    "recent_research", research[:1000],
                )
        except Exception as exc:
            logger.warning("Failed to pre-load shared memory: %s", exc)

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
