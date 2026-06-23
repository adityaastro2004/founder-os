"""
Founder OS — Workflow IR (Intermediate Representation), frozen v1.

The single load-bearing contract for the n8n-backed workflow system (ADR-008,
O-1 / O-1-AMEND). `Workflow.steps` (JSONB) stores ONE envelope:

    {"ir_version": 1, "trigger": {...}, "steps": [ <node>, ... ]}

The Orchestrator emits exactly this; the compiler reads exactly this; neither
side parses n8n JSON. v1 is **linear** (`depends_on` is a single-predecessor
chain; branching is v3).

Security invariants enforced here (O-1-AMEND HARD RULES — `validate_ir`):
  1. `action` steps are LOW-risk-tool ONLY. Risk is derived server-side from the
     tool name via `app.agents.approval.classify_tool_risk`; a MEDIUM/HIGH tool
     (incl. any unknown/MCP tool, which defaults to MEDIUM) is a validation error.
  2. Risk is NEVER declared in the IR. Any risk-like field on a node is rejected.
  3. Unknown `ir_version` is rejected, not guessed.
  4. `agent` ∈ registry slugs; `action.tool` is a non-empty string.

`classify_tool_risk` / `TOOL_RISK_MAP` are reused verbatim from
`app/agents/approval.py` — risk classification is the load-bearing security
control (C-8) and is never duplicated here.
"""

from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from app.agents.agents import AGENT_CLASSES
from app.agents.approval import RiskLevel, classify_tool_risk

# The only IR version this code understands. A future shape bump increments this
# and the compiler branches on it; v1 rejects any other version (O-1-AMEND #4).
IR_VERSION: int = 1

# Risk-like field names that MUST NOT appear on any node (O-1-AMEND #2 / C-8).
# Risk is derived only server-side by tool name; declaring it in the IR is an
# attempt to smuggle a downgrade and is rejected.
_FORBIDDEN_RISK_FIELDS: frozenset[str] = frozenset(
    {"risk", "risk_level", "risklevel", "risk_tier", "requires_approval"}
)

# Valid specialist agent slugs (registry AGENT_CLASSES keys).
AGENT_SLUGS: frozenset[str] = frozenset(AGENT_CLASSES.keys())


# ============================================================================
# Triggers (v1: manual | cron — webhook/event reserved for v2)
# ============================================================================

class ManualTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["manual"] = "manual"


class CronTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["cron"]
    cron: str = Field(..., description="5-field cron expression, e.g. '0 3 * * 1'")
    timezone: str = "Asia/Kolkata"


Trigger = Union[ManualTrigger, CronTrigger]


# ============================================================================
# Step nodes (agent | action). `extra="forbid"` rejects smuggled fields incl. risk.
# ============================================================================

class AgentStep(BaseModel):
    """An agent run step. Runs in no-side-effect / content-analysis mode (O-3-AMEND-2)."""
    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["agent"]
    agent: str = Field(..., description="specialist slug (registry AGENT_CLASSES key)")
    instruction: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class ActionStep(BaseModel):
    """A direct, risk-classified tool action. v1: LOW-risk tools only (O-1-AMEND #1)."""
    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["action"]
    agent: str = Field(..., description="the agent context the tool runs under")
    tool: str = Field(..., description="a real tool name from the ToolRegistry")
    arguments: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


Step = Union[AgentStep, ActionStep]


class WorkflowIR(BaseModel):
    """The frozen v1 envelope stored in `Workflow.steps` (JSONB)."""
    model_config = ConfigDict(extra="forbid")

    ir_version: int
    trigger: Trigger = Field(..., discriminator="type")
    steps: list[Step]


# ============================================================================
# Validation — O-1-AMEND HARD RULES (also re-enforced server-side at callback/step)
# ============================================================================

def validate_ir(ir: Union[WorkflowIR, dict[str, Any]]) -> list[str]:
    """
    Validate a workflow IR and return a list of human-readable error strings.
    An empty list means the IR is valid and safe to compile/push.

    Enforces the O-1-AMEND hard rules + the Contract-1 structural rules. This is
    the same logic the callback re-runs server-side per `step_id` (C-8): risk is
    derived ONLY via `classify_tool_risk(tool)`; the IR may never declare it.
    """
    errors: list[str] = []

    raw: dict[str, Any]
    if isinstance(ir, WorkflowIR):
        raw = ir.model_dump()
    elif isinstance(ir, dict):
        raw = ir
    else:
        return [f"IR must be a dict or WorkflowIR, got {type(ir).__name__}."]

    # Rule 4: unknown ir_version is rejected, not guessed.
    version = raw.get("ir_version")
    if version != IR_VERSION:
        errors.append(
            f"Unsupported ir_version {version!r}; this build only understands ir_version {IR_VERSION}."
        )
        # Version mismatch means we cannot trust the rest of the shape — stop here.
        return errors

    # Structural shape via Pydantic (extra='forbid' rejects unknown/smuggled fields,
    # which already covers most risk-field smuggling — Rule 2).
    try:
        parsed = WorkflowIR.model_validate(raw)
    except Exception as exc:  # pydantic ValidationError — surface readably (FR-3)
        errors.append(f"IR does not match the v1 schema: {exc}")
        return errors

    # Rule 2 (belt-and-suspenders): explicitly reject any risk-like field smuggled
    # into a raw node even if a future model loosened `extra`. Risk is server-side only.
    for raw_step in raw.get("steps", []):
        if isinstance(raw_step, dict):
            smuggled = _FORBIDDEN_RISK_FIELDS.intersection(k.lower() for k in raw_step.keys())
            if smuggled:
                sid = raw_step.get("id", "<no-id>")
                errors.append(
                    f"Step {sid!r} declares a risk field {sorted(smuggled)}; "
                    f"risk is classified server-side by tool name and must never appear in the IR."
                )

    steps = parsed.steps
    if not steps:
        errors.append("IR must contain at least one step.")

    # Unique ids
    seen_ids: set[str] = set()
    for step in steps:
        if not step.id:
            errors.append("Every step must have a non-empty id.")
            continue
        if step.id in seen_ids:
            errors.append(f"Duplicate step id {step.id!r}; step ids must be unique.")
        seen_ids.add(step.id)

    for step in steps:
        # depends_on must reference earlier, existing ids (linear chain; v1).
        for dep in step.depends_on:
            if dep == step.id:
                errors.append(f"Step {step.id!r} cannot depend on itself.")
            elif dep not in seen_ids:
                errors.append(
                    f"Step {step.id!r} depends_on {dep!r}, which is not a known earlier step id."
                )
        if len(step.depends_on) > 1:
            errors.append(
                f"Step {step.id!r} has {len(step.depends_on)} predecessors; "
                f"v1 IR is linear (single-predecessor chain). Branching is v3."
            )

        # agent slug must exist in the registry (C-8).
        if step.agent not in AGENT_SLUGS:
            errors.append(
                f"Step {step.id!r} names unknown agent {step.agent!r}; "
                f"valid agents: {sorted(AGENT_SLUGS)}."
            )

        # Rule 1: action steps are LOW-risk-tool only. Classify server-side by name.
        if isinstance(step, ActionStep):
            if not step.tool or not step.tool.strip():
                errors.append(f"Action step {step.id!r} must name a non-empty tool.")
                continue
            risk = classify_tool_risk(step.tool)
            if risk is not RiskLevel.LOW:
                errors.append(
                    f"Action step {step.id!r} uses tool {step.tool!r} classified {risk.value.upper()}; "
                    f"v1 action steps are LOW-risk only. MEDIUM/HIGH actions are out of v1 scope "
                    f"(deferred to the v2 gated Wait-node path)."
                )

    return errors


# ============================================================================
# Serialization — to/from the JSONB stored in Workflow.steps
# ============================================================================

def parse_ir(stored: Union[dict[str, Any], WorkflowIR]) -> WorkflowIR:
    """
    Deserialize the JSONB envelope from `Workflow.steps` into a typed WorkflowIR.

    Raises a pydantic ValidationError if the shape is wrong. This does NOT run the
    O-1-AMEND security rules — call `validate_ir` for that (e.g. before compile and
    server-side at callback/step).
    """
    if isinstance(stored, WorkflowIR):
        return stored
    return WorkflowIR.model_validate(stored)


def serialize_ir(ir: WorkflowIR) -> dict[str, Any]:
    """
    Serialize a typed WorkflowIR to the plain JSONB dict stored in `Workflow.steps`.
    Round-trips with `parse_ir`.
    """
    return ir.model_dump(mode="json")


def get_step(ir: Union[dict[str, Any], WorkflowIR], step_id: str) -> Optional[Step]:
    """
    Load the authoritative step from a persisted IR by id (O-1 / C-2 / C-8).

    The callback MUST resolve a step's tool/agent from the persisted IR by id —
    never from the n8n request body — so an n8n-side edit cannot downgrade risk.
    """
    parsed = parse_ir(ir)
    for step in parsed.steps:
        if step.id == step_id:
            return step
    return None
