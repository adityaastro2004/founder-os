"""
Founder OS — Workflow IR generation (Wave 2b / ADR-008, US-1).

Turns a founder's natural-language goal into a valid workflow IR (the frozen v1
envelope in `app/workflows/ir.py`). This is the heart of the "auto-generated
workflows" differentiator: the founder describes a recurring outcome and the
Orchestrator emits a runnable plan — no manual step authoring.

Design (mirrors `app/agents/generator.py`, the agent-definition generator):
  - Provider-neutral: takes an `LLMProvider` and calls `generate()` (never a
    vendor SDK). The default provider is Ollama; any provider works.
  - The prompt CONSTRAINS the model to: real specialist agent slugs only,
    `action` steps with LOW-risk tools only, a linear chain, and a manual/cron
    trigger. The model is told risk is never declared in the IR.
  - Tolerant JSON parsing of the reply (prose-wrapped JSON is recovered).
  - The result is ALWAYS run through `validate_ir` (ADR-008 O-1-AMEND hard rules).
    The constraints in the prompt are a best-effort steer; `validate_ir` is the
    load-bearing security control (C-8) — an invalid IR is never returned, never
    persisted. On failure we repair-prompt ONCE, then raise a clear error.

This module does NOT persist, compile, or push. Wave 3 wires generate → persist
(via `app.workflows.service.create_workflow`) → compile → push to n8n.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from app.agents.agents import AGENT_CLASSES
from app.agents.approval import RiskLevel, classify_tool_risk
from app.agents.llm import LLMMessage, LLMProvider, Role
from app.workflows.ir import IR_VERSION, validate_ir

logger = logging.getLogger(__name__)


class WorkflowGenerationError(Exception):
    """Raised when a valid workflow IR could not be generated (FR-3 actionable error)."""

    def __init__(self, message: str, *, errors: Optional[list[str]] = None) -> None:
        super().__init__(message)
        self.errors = errors or []


# Default agent slugs available for generation (registry AGENT_CLASSES keys, minus
# the orchestrator itself — a workflow step delegates to a *specialist*).
DEFAULT_WORKFLOW_AGENTS: list[str] = [
    slug for slug in AGENT_CLASSES.keys() if slug != "orchestrator"
]


def _registry_candidate_tools() -> list[str]:
    """The agents' declared tools, de-duped — reuse what the registry knows."""
    seen: set[str] = set()
    out: list[str] = []
    for cls in AGENT_CLASSES.values():
        for tool in getattr(cls, "default_tools", []) or []:
            if tool not in seen:
                seen.add(tool)
                out.append(tool)
    return out


# Computed once at import: AGENT_CLASSES and the risk map are static for the
# process lifetime, so the no-argument menu never changes (mirrors
# DEFAULT_WORKFLOW_AGENTS above). Per-call filtering only runs when a caller
# passes an explicit candidate list.
_DEFAULT_LOW_RISK_TOOLS: list[str] = [
    t for t in _registry_candidate_tools() if classify_tool_risk(t) is RiskLevel.LOW
]


def default_low_risk_tools(candidates: Optional[list[str]] = None) -> list[str]:
    """
    The LOW-risk tool menu offered to the generator.

    `action` steps are LOW-risk only (O-1-AMEND #1). We derive the menu by
    classifying each candidate tool server-side via `classify_tool_risk` — the
    same control `validate_ir` re-applies — so the prompt can only ever offer
    tools that will pass validation. Unknown tools default to MEDIUM and are
    therefore excluded.
    """
    if candidates is None:
        return list(_DEFAULT_LOW_RISK_TOOLS)
    return [t for t in candidates if classify_tool_risk(t) is RiskLevel.LOW]


_SYSTEM = (
    "You are the workflow generator for Founder OS. Given a founder's plain-language "
    "goal, you design a RUNNABLE workflow as STRICT JSON in the frozen v1 IR schema "
    "below — nothing else, no prose, no markdown fences.\n\n"
    "HARD RULES (a workflow violating any of these is rejected and useless):\n"
    "  1. Output exactly one JSON object: "
    '{"ir_version": 1, "trigger": {...}, "steps": [ ... ]}.\n'
    "  2. trigger is EITHER {\"type\":\"manual\"} OR "
    '{"type":"cron","cron":"<5-field cron>","timezone":"Asia/Kolkata"}. '
    "Use cron only when the goal is recurring/scheduled; otherwise manual.\n"
    "  3. Each step is an object with a unique string id (s1, s2, ...). The steps "
    "form a LINEAR chain: the first step has depends_on=[], every later step has "
    'depends_on=["<id of the immediately preceding step>"]. No branching.\n'
    "  4. A step is one of two types:\n"
    "     - agent step: "
    '{"id","type":"agent","agent":"<slug>","instruction":"<text>","inputs":{},"depends_on":[...]}. '
    "Agent steps do CONTENT and ANALYSIS only (summarise, draft, research, plan).\n"
    "     - action step: "
    '{"id","type":"action","agent":"<slug>","tool":"<tool>","arguments":{},"depends_on":[...]}. '
    "An action step runs a single tool.\n"
    "  5. agent MUST be one of the provided agent slugs. tool MUST be one of the "
    "provided LOW-risk tools — these are the ONLY tools allowed in an action step. "
    "Do NOT use any tool that sends, posts, pays, deploys, or deletes.\n"
    "  6. NEVER add a risk/risk_level/requires_approval field. Risk is decided by "
    "the server from the tool name; declaring it is forbidden and rejected.\n"
    "  7. Produce at least one step. Prefer the smallest coherent plan that achieves "
    "the goal.\n"
)


def _build_user_prompt(
    goal: str,
    *,
    available_agents: list[str],
    available_low_risk_tools: list[str],
    context: Optional[str],
) -> str:
    ctx = f"\nFOUNDER CONTEXT:\n{context}\n" if context else ""
    return (
        f"FOUNDER GOAL:\n{goal}\n"
        f"{ctx}\n"
        f"AVAILABLE AGENT SLUGS (use only these for `agent`): {available_agents}\n"
        f"AVAILABLE LOW-RISK TOOLS (use only these for an action step's `tool`): "
        f"{available_low_risk_tools}\n\n"
        f"Respond with the STRICT JSON IR object only."
    )


def _parse_ir_json(raw: str) -> Optional[dict[str, Any]]:
    """
    Parse the LLM reply into an IR dict; tolerant of prose-wrapped JSON.

    Mirrors `app/agents/generator.py:_parse_definition` — slice from the first `{`
    to the last `}` and json.loads. Returns None if no JSON object is recoverable.
    """
    text = (raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


async def _ask_llm(llm: LLMProvider, system: str, user: str) -> str:
    """Single provider-neutral completion returning text. Low temperature for
    deterministic, schema-faithful JSON."""
    response = await llm.generate(
        [LLMMessage(role=Role.USER, content=user)],
        system=system,
        temperature=0.2,
        max_tokens=2048,
    )
    return response.content or ""


async def generate_workflow_ir(
    llm: LLMProvider,
    goal: str,
    *,
    available_agents: Optional[list[str]] = None,
    available_low_risk_tools: Optional[list[str]] = None,
    context: Optional[str] = None,
) -> dict[str, Any]:
    """
    Generate a validated workflow IR (the v1 envelope) from a natural-language goal.

    Args:
        llm: any `LLMProvider` (provider-neutral; no vendor coupling).
        goal: the founder's plain-language outcome to automate.
        available_agents: specialist slugs the generator may use. Defaults to the
            registry specialists (excluding the orchestrator).
        available_low_risk_tools: LOW-risk tool names allowed in `action` steps.
            Defaults to the registry's LOW-risk tools (derived via
            `classify_tool_risk`). Any non-LOW tool passed here is filtered out so
            the prompt can never offer a tool that `validate_ir` would reject.
        context: optional founder/business context to specialise the plan.

    Returns:
        The serialized IR dict, guaranteed to pass `validate_ir` (safe to persist
        via `app.workflows.service.create_workflow(..., steps=ir)`).

    Raises:
        WorkflowGenerationError: if the model never produced a parseable, valid IR
            (after one repair attempt). The error carries the validation messages
            so the caller can surface an actionable, human-readable message (FR-3).
            An invalid IR is NEVER returned and NEVER persisted (O-1-AMEND / C-8).
    """
    if not goal or not goal.strip():
        raise WorkflowGenerationError("A non-empty goal is required to generate a workflow.")

    agents = list(available_agents) if available_agents is not None else DEFAULT_WORKFLOW_AGENTS
    # Re-derive/filter the tool menu server-side so a caller can never widen it to a
    # non-LOW tool (defence-in-depth alongside validate_ir).
    if available_low_risk_tools is not None:
        tools = [t for t in available_low_risk_tools if classify_tool_risk(t) is RiskLevel.LOW]
    else:
        tools = default_low_risk_tools()

    user_prompt = _build_user_prompt(
        goal,
        available_agents=agents,
        available_low_risk_tools=tools,
        context=context,
    )

    # --- First attempt ----------------------------------------------------
    raw = await _ask_llm(llm, _SYSTEM, user_prompt)
    ir = _parse_ir_json(raw)
    errors: list[str]
    if ir is None:
        errors = ["The model did not return parseable JSON for the workflow IR."]
    else:
        ir.setdefault("ir_version", IR_VERSION)  # tolerate an omitted version
        errors = validate_ir(ir)
        if not errors:
            logger.info("generate_workflow_ir: valid IR on first attempt (%d steps)", len(ir.get("steps", [])))
            return ir

    # --- One repair attempt: feed the errors back and re-ask --------------
    logger.info("generate_workflow_ir: first attempt invalid (%d errors) — repairing", len(errors))
    repair_prompt = (
        f"{user_prompt}\n\n"
        f"Your previous output was REJECTED for these reasons:\n"
        + "\n".join(f"  - {e}" for e in errors)
        + "\n\nReturn a corrected STRICT JSON IR object that fixes every issue above. "
        "Remember: action steps may ONLY use the listed LOW-risk tools, agents MUST "
        "be from the listed slugs, no risk fields, linear depends_on chain."
    )
    raw = await _ask_llm(llm, _SYSTEM, repair_prompt)
    ir = _parse_ir_json(raw)
    if ir is None:
        raise WorkflowGenerationError(
            "Could not generate a valid workflow from that goal — the model did not "
            "return usable JSON. Please rephrase the goal and try again.",
            errors=errors,
        )
    ir.setdefault("ir_version", IR_VERSION)
    errors = validate_ir(ir)
    if errors:
        raise WorkflowGenerationError(
            "Could not generate a valid workflow from that goal. "
            "Try describing it more concretely (what should run, when, and which "
            "specialist should handle each part).",
            errors=errors,
        )
    logger.info("generate_workflow_ir: valid IR after repair (%d steps)", len(ir.get("steps", [])))
    return ir
