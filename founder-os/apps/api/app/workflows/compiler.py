"""
Founder OS — IR → n8n workflow JSON compiler (ADR-008, Track D / D2).

Translates the frozen v1 workflow IR (`app/workflows/ir.py`, Contract 1) into the
n8n workflow JSON that is pushed to a self-hosted n8n instance (Contract 2). The
compile is **one-way**: n8n JSON is a build artifact and is never parsed back into
IR (ADR-008). This module is **pure** — no IO, no network, no DB; it takes an IR
plus the injected dependencies it needs and returns a dict.

What the compiler emits (Contract 2):
  - A **trigger** node:
      * always a **Manual Trigger** (so "run now" via REST works); and
      * when `trigger.type == "cron"`, additionally a **Schedule Trigger** node
        carrying the cron expression — n8n owns ALL workflow scheduling
        (O-4-AMEND: n8n is the sole scheduler of record; Founder OS adds no
        APScheduler job for workflows).
  - A **start callback** HTTP node that POSTs to `/api/workflows/callback/start`
    (creates the WorkflowExecution; returns execution_id).
  - One **HTTP Request node per IR step** that POSTs to
    `/api/workflows/callback/step` with the per-node signed token in the
    `X-FOS-Workflow-Token` header. The node carries NO logic, NO credentials, and
    NO `user_id` — the server resolves the authoritative step from the persisted
    IR by `step_id` and derives identity from the verified token (O-1 / O-2).
  - A **finish callback** HTTP node that POSTs to `/api/workflows/callback/finish`.
  - Linear `depends_on` chain → sequential node connections.

Security boundaries enforced here:
  - The ONLY secret that ever appears in the emitted JSON is the per-node signed
    token returned by `sign_token_fn`. The master `WORKFLOW_CALLBACK_SECRET`
    NEVER appears (C-5). This module does not have and does not want the secret;
    it asks the injected `sign_token_fn` to mint a token per (workflow, user, step).
  - Risk is never written into the n8n JSON — the server re-classifies by tool
    name from the persisted IR (O-1-AMEND / C-8). The compiler does not branch on
    risk; gating is a server-side + (v2) Wait-node concern.

NOTE on the v1 gate (O-3-AMEND-1): in v1 the IR validator forbids non-LOW
`action` tools and agent steps run no-side-effect, so no step takes the gated
Wait-node path. The Wait-node compile machinery is therefore NOT emitted here in
v1 (it is the v2 home for gated MEDIUM/HIGH actions). This is flagged in the
module-level "Design gaps / Wave-3 contract" docstring below; do not add Wait
nodes without the resolver + resume-URL plumbing they require.

────────────────────────────────────────────────────────────────────────────────
sign_token_fn contract (the dependency Wave 3 / the callback-auth track MUST
satisfy — HMAC is implemented there, NOT here):

    def sign_token_fn(workflow_id: str, user_id: str, step_id: str | None) -> str

  - Returns the value to place in the `X-FOS-Workflow-Token` header for a single
    n8n HTTP node. Per ADR-008 O-2 this is `base64(payload).signature` where
    `payload = {workflow_id, user_id, iat, kid}` and the signature is
    `HMAC-SHA256(key = WORKFLOW_CALLBACK_SECRET[kid] + ":" + workflow_id,
    msg = canonical(payload))`.
  - `step_id` is `None` for the workflow-boundary nodes (start / finish) and the
    concrete step id for per-step nodes. Wave 3 MAY bind the token to the step
    (single-use-per-step, C-1) or mint a workflow-scoped token and rely on the
    server-side execution/step binding (C-2) — the compiler is agnostic; it only
    requires that the returned string is the exact header value to bake.
  - MUST raise if the master secret is absent/weak when compiling a workflow
    (O-2-AMEND #1: the compiler must refuse to compile/push without a present,
    strong secret). The compiler propagates that error to the caller (FR-3).
  - MUST NEVER return the master secret itself or anything from which it can be
    derived; the only thing that lands in n8n is this opaque token (C-5).
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional, Union

from app.workflows.ir import (
    ActionStep,
    AgentStep,
    CronTrigger,
    WorkflowIR,
    parse_ir,
)

# The dependency the callback-auth track (Wave 3) injects. See module docstring.
SignTokenFn = Callable[[str, str, Optional[str]], str]

# Callback paths (Contract 3). Joined onto callback_base_url at compile time.
_CALLBACK_START = "/api/workflows/callback/start"
_CALLBACK_STEP = "/api/workflows/callback/step"
_CALLBACK_FINISH = "/api/workflows/callback/finish"

# The header n8n HTTP nodes carry the per-node signed token in (O-2).
_TOKEN_HEADER = "X-FOS-Workflow-Token"

# n8n expression that threads the execution_id from the Start node's response into
# a downstream callback body (Contract 3). Single source of truth for the key the
# start callback returns and downstream nodes read.
_EXECUTION_ID_EXPR = "={{ $json.execution_id }}"

# n8n node type identifiers (n8n-nodes-base.*) used by the compiler.
_NODE_MANUAL_TRIGGER = "n8n-nodes-base.manualTrigger"
_NODE_SCHEDULE_TRIGGER = "n8n-nodes-base.scheduleTrigger"
_NODE_HTTP_REQUEST = "n8n-nodes-base.httpRequest"

# Canvas layout — purely cosmetic for the n8n editor.
_X_START = 240
_X_STEP = 220
_Y_TRIGGER = 300


def compile_ir_to_n8n(
    workflow_id: str,
    ir: Union[WorkflowIR, dict[str, Any]],
    *,
    user_id: str,
    callback_base_url: str,
    sign_token_fn: SignTokenFn,
) -> dict[str, Any]:
    """
    Compile a workflow IR into n8n workflow JSON (Contract 2).

    Args:
        workflow_id: the Founder OS Workflow id (uuid str). Baked into callback
            bodies and passed to `sign_token_fn`; it is non-secret.
        ir: the frozen v1 IR (typed WorkflowIR or its JSONB dict). Assumed already
            validated by `validate_ir`; the compiler re-parses for type safety but
            does not re-run the security rules (callers validate before compile).
        user_id: the owning user. Passed ONLY to `sign_token_fn` so the token can
            bind identity. It is NOT written into any n8n node body — the server
            derives the user from the verified token, never from the request body
            (O-2). Kept out of the emitted JSON entirely.
        callback_base_url: the base URL n8n uses to reach the Founder OS API. This
            MUST be the host-reachable form (e.g. http://host.docker.internal:8000
            from WORKFLOW_CALLBACK_BASE_URL), NOT localhost, because the callbacks
            run from inside the n8n container.
        sign_token_fn: injected token minter (see module docstring contract).

    Returns:
        A dict ready to push via N8nClient.create_workflow. One-way artifact.
    """
    parsed = parse_ir(ir)
    base = callback_base_url.rstrip("/")

    nodes: list[dict[str, Any]] = []
    # connections maps a node NAME → its outgoing "main" connections (n8n format).
    connections: dict[str, Any] = {}

    # -- 1. Trigger node(s) ------------------------------------------------
    manual_trigger = _manual_trigger_node(x=_X_START, y=_Y_TRIGGER)
    nodes.append(manual_trigger)
    entry_node_names = [manual_trigger["name"]]

    if isinstance(parsed.trigger, CronTrigger):
        schedule = _schedule_trigger_node(
            cron=parsed.trigger.cron,
            timezone=parsed.trigger.timezone,
            x=_X_START,
            y=_Y_TRIGGER + 160,
        )
        nodes.append(schedule)
        entry_node_names.append(schedule["name"])

    # -- 2. Start callback node -------------------------------------------
    x = _X_START + _X_STEP
    start_node = _http_callback_node(
        name="FOS Start",
        url=f"{base}{_CALLBACK_START}",
        token=sign_token_fn(workflow_id, user_id, None),
        body={"workflow_id": workflow_id},
        x=x,
        y=_Y_TRIGGER,
    )
    nodes.append(start_node)
    # Every trigger flows into the start callback.
    for trigger_name in entry_node_names:
        _connect(connections, trigger_name, start_node["name"])

    prev_name = start_node["name"]

    # -- 3. One HTTP node per IR step (linear chain) ----------------------
    for step in parsed.steps:
        x += _X_STEP
        step_node = _http_callback_node(
            name=_step_node_name(step),
            url=f"{base}{_CALLBACK_STEP}",
            token=sign_token_fn(workflow_id, user_id, step.id),
            # The body carries identifiers ONLY. The server loads the
            # authoritative step (tool/agent/args) from the persisted IR by
            # step_id and ignores anything else (O-1 / C-8). execution_id is
            # threaded from the Start node's response at runtime.
            body={
                "workflow_id": workflow_id,
                "execution_id": _EXECUTION_ID_EXPR,
                "step_id": step.id,
            },
            x=x,
            y=_Y_TRIGGER,
        )
        nodes.append(step_node)
        _connect(connections, prev_name, step_node["name"])
        prev_name = step_node["name"]

    # -- 4. Finish callback node ------------------------------------------
    x += _X_STEP
    finish_node = _http_callback_node(
        name="FOS Finish",
        url=f"{base}{_CALLBACK_FINISH}",
        token=sign_token_fn(workflow_id, user_id, None),
        body={
            "workflow_id": workflow_id,
            "execution_id": _EXECUTION_ID_EXPR,
            "status": "completed",
        },
        x=x,
        y=_Y_TRIGGER,
    )
    nodes.append(finish_node)
    _connect(connections, prev_name, finish_node["name"])

    # n8n workflow envelope. `active: False` — activation is an explicit client
    # call after create (N8nClient.activate_workflow), per Track G.
    return {
        "name": f"FOS Workflow {workflow_id}",
        "nodes": nodes,
        "connections": connections,
        "active": False,
        "settings": {"executionOrder": "v1"},
    }


# ============================================================================
# Node builders (pure)
# ============================================================================

def _manual_trigger_node(*, x: int, y: int) -> dict[str, Any]:
    return {
        "id": "fos-manual-trigger",
        "name": "Manual Trigger",
        "type": _NODE_MANUAL_TRIGGER,
        "typeVersion": 1,
        "position": [x, y],
        "parameters": {},
    }


def _schedule_trigger_node(*, cron: str, timezone: str, x: int, y: int) -> dict[str, Any]:
    """n8n Schedule Trigger carrying the cron expression (O-4: n8n owns cron)."""
    return {
        "id": "fos-schedule-trigger",
        "name": "Schedule Trigger",
        "type": _NODE_SCHEDULE_TRIGGER,
        "typeVersion": 1,
        "position": [x, y],
        "parameters": {
            "rule": {
                "interval": [
                    {
                        "field": "cronExpression",
                        "expression": cron,
                    }
                ]
            },
            # Display/eval timezone for the schedule.
            "timezone": timezone,
        },
    }


def _http_callback_node(
    *,
    name: str,
    url: str,
    token: str,
    body: dict[str, Any],
    x: int,
    y: int,
) -> dict[str, Any]:
    """
    An n8n HTTP Request node that POSTs a JSON body to a Founder OS callback URL
    with the per-node signed token in the X-FOS-Workflow-Token header.

    The token is the ONLY secret in the node; the master secret never appears.
    """
    return {
        "id": _slug(name),
        "name": name,
        "type": _NODE_HTTP_REQUEST,
        "typeVersion": 4,
        "position": [x, y],
        "parameters": {
            "method": "POST",
            "url": url,
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": _TOKEN_HEADER, "value": token},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": _json_body_expr(body),
            "options": {},
        },
    }


def _json_body_expr(body: dict[str, Any]) -> str:
    """
    Render the JSON body for an n8n HTTP node.

    n8n expects the JSON body as a string; values that begin with "=" are n8n
    expressions (e.g. threading execution_id from a prior node's response). We
    build a small object literal so static values are quoted and expression
    values (prefixed "=") are emitted as n8n expression references.
    """
    parts: list[str] = []
    for key, value in body.items():
        if isinstance(value, str) and value.startswith("="):
            # n8n expression — strip the leading "=" marker, emit as {{ ... }}.
            expr = value[1:].strip()
            parts.append(f'  "{key}": {expr}')
        else:
            # Static value — JSON-encode it.
            parts.append(f'  "{key}": {json.dumps(value)}')
    inner = ",\n".join(parts)
    # The "=" prefix tells n8n the whole field is an expression-evaluated string.
    return "={\n" + inner + "\n}"


def _connect(connections: dict[str, Any], from_name: str, to_name: str) -> None:
    """Wire from_name → to_name on the main output (n8n connection format)."""
    entry = connections.setdefault(from_name, {})
    main = entry.setdefault("main", [[]])
    main[0].append({"node": to_name, "type": "main", "index": 0})


def _step_node_name(step: Union[AgentStep, ActionStep]) -> str:
    if isinstance(step, ActionStep):
        return f"Step {step.id} (action: {step.tool})"
    return f"Step {step.id} (agent: {step.agent})"


def _slug(name: str) -> str:
    return "fos-" + "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")
