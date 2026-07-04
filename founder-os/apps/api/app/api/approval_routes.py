"""
Founder OS — Approval API Routes
===================================
Endpoints for managing the human-in-the-loop approval system.

Users can:
  - List pending approvals
  - Approve or reject an action
  - Set "always allow" / "always deny" per tool
  - View and manage their approval preferences
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ClerkUser, require_auth
from app.database import get_db
from app.redis import get_redis
from app.agents.approval import (
    ApprovalGate,
    ApprovalPreferences,
    HIGH_RISK_TOOLS,
    RiskLevel,
    classify_tool_risk,
)

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


# ── Request / Response models ─────────────────────────────

class ApprovalActionRequest(BaseModel):
    note: Optional[str] = Field(None, description="Optional note explaining the decision")


class SetPreferenceRequest(BaseModel):
    tool_name: str = Field(..., description="Tool to set preference for")
    preference: str = Field(
        ...,
        description="One of: always_allow, always_deny, ask",
        pattern="^(always_allow|always_deny|ask)$",
    )


class PendingApprovalResponse(BaseModel):
    id: str
    tool_name: str
    arguments: dict
    risk_level: str
    agent_name: str
    session_id: str
    description: str
    created_at: float
    expires_at: float
    status: str
    can_always_allow: bool = True  # False for HIGH-risk tools


class ApprovalPreferenceResponse(BaseModel):
    tool_name: str
    preference: str
    risk_level: str
    is_high_risk: bool


class ApprovalResolveResponse(BaseModel):
    id: str
    tool_name: str
    status: str
    resolution_note: str


class ToolRiskInfo(BaseModel):
    tool_name: str
    risk_level: str
    can_always_allow: bool
    # None = unset → default policy (LOW/MEDIUM auto-approve, HIGH gates).
    # Distinct from explicit "ask", which always gates (F2/S2).
    current_preference: str | None = None


# ── Helpers ───────────────────────────────────────────────

async def _get_user_id(user: ClerkUser) -> str:
    """Resolve the REAL users.id (as a string — approvals are keyed in Redis).

    Must match the id agents run under (the registry builds agents with the real
    users.id), else pending approvals created during a run are invisible here.
    Opens its own short-lived session since these endpoints are Redis-only.
    """
    from app.database import async_session
    from app.users import get_or_create_user_id

    async with async_session() as session:
        uid = await get_or_create_user_id(user.user_id, session, email=user.email)
        await session.commit()
    return str(uid)


# ── Routes ────────────────────────────────────────────────

@router.get("/pending", response_model=list[PendingApprovalResponse])
async def list_pending_approvals(
    user: ClerkUser = Depends(require_auth),
):
    """List all pending approvals for the current user."""
    redis = get_redis()
    gate = ApprovalGate(redis)
    user_id = await _get_user_id(user)

    pending = await gate.list_pending(user_id)

    return [
        PendingApprovalResponse(
            id=p.id,
            tool_name=p.tool_name,
            arguments=p.arguments,
            risk_level=p.risk_level,
            agent_name=p.agent_name,
            session_id=p.session_id,
            description=p.description,
            created_at=p.created_at,
            expires_at=p.expires_at,
            status=p.status,
            can_always_allow=p.tool_name not in HIGH_RISK_TOOLS,
        )
        for p in pending
    ]


@router.post("/{approval_id}/approve", response_model=ApprovalResolveResponse)
async def approve_action(
    approval_id: str,
    body: ApprovalActionRequest = ApprovalActionRequest(),
    user: ClerkUser = Depends(require_auth),
):
    """
    Approve a pending action.

    Once approved, the action will be executed the next time
    the agent is re-run, or can be executed immediately via
    the /execute endpoint.
    """
    redis = get_redis()
    gate = ApprovalGate(redis)
    user_id = await _get_user_id(user)

    # Verify the approval belongs to this user
    approval = await gate.preferences.get_pending(approval_id)
    if not approval or approval.user_id != user_id:
        raise HTTPException(status_code=404, detail="Approval not found")

    if approval.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Approval already resolved: {approval.status}",
        )

    result = await gate.approve(approval_id, note=body.note or "")
    if not result:
        raise HTTPException(status_code=404, detail="Approval not found or expired")

    return ApprovalResolveResponse(
        id=result.id,
        tool_name=result.tool_name,
        status=result.status,
        resolution_note=result.resolution_note,
    )


@router.post("/{approval_id}/reject", response_model=ApprovalResolveResponse)
async def reject_action(
    approval_id: str,
    body: ApprovalActionRequest = ApprovalActionRequest(),
    user: ClerkUser = Depends(require_auth),
):
    """Reject a pending action. The tool call will not be executed."""
    redis = get_redis()
    gate = ApprovalGate(redis)
    user_id = await _get_user_id(user)

    approval = await gate.preferences.get_pending(approval_id)
    if not approval or approval.user_id != user_id:
        raise HTTPException(status_code=404, detail="Approval not found")

    if approval.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Approval already resolved: {approval.status}",
        )

    result = await gate.reject(approval_id, note=body.note or "")
    if not result:
        raise HTTPException(status_code=404, detail="Approval not found or expired")

    return ApprovalResolveResponse(
        id=result.id,
        tool_name=result.tool_name,
        status=result.status,
        resolution_note=result.resolution_note,
    )


@router.get("/preferences", response_model=list[ApprovalPreferenceResponse])
async def get_preferences(
    user: ClerkUser = Depends(require_auth),
):
    """Get all approval preferences for the current user."""
    redis = get_redis()
    prefs = ApprovalPreferences(redis)
    user_id = await _get_user_id(user)

    all_prefs = await prefs.get_all_preferences(user_id)

    return [
        ApprovalPreferenceResponse(
            tool_name=tool,
            preference=pref,
            risk_level=classify_tool_risk(tool).value,
            is_high_risk=tool in HIGH_RISK_TOOLS,
        )
        for tool, pref in all_prefs.items()
    ]


@router.post("/preferences", response_model=ApprovalPreferenceResponse)
async def set_preference(
    body: SetPreferenceRequest,
    user: ClerkUser = Depends(require_auth),
):
    """
    Set an approval preference for a tool.

    Options:
      - "always_allow" — auto-approve (NOT available for high-risk tools)
      - "always_deny"  — auto-reject
      - "ask"          — always ask before running

    Unset (no preference) = default policy: LOW/MEDIUM auto-approve,
    HIGH always requires approval. Setting "ask" makes the tool gate.

    High-risk tools (PR push, social media posting, payments, deployments)
    cannot be set to "always_allow". This is enforced server-side.
    """
    redis = get_redis()
    prefs = ApprovalPreferences(redis)
    user_id = await _get_user_id(user)

    risk = classify_tool_risk(body.tool_name)
    is_high = body.tool_name in HIGH_RISK_TOOLS

    if body.preference == "always_allow" and is_high:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Cannot set 'always_allow' for high-risk tool '{body.tool_name}'. "
                f"High-risk actions always require explicit approval."
            ),
        )

    success = await prefs.set_preference(user_id, body.tool_name, body.preference)
    if not success:
        raise HTTPException(status_code=403, detail="Preference not allowed")

    return ApprovalPreferenceResponse(
        tool_name=body.tool_name,
        preference=body.preference,
        risk_level=risk.value,
        is_high_risk=is_high,
    )


@router.delete("/preferences/{tool_name}")
async def clear_preference(
    tool_name: str,
    user: ClerkUser = Depends(require_auth),
):
    """Clear a tool preference — reverts to UNSET (default policy: LOW/MEDIUM
    auto-approve, HIGH always gates). To be asked every time, set "ask"."""
    redis = get_redis()
    prefs = ApprovalPreferences(redis)
    user_id = await _get_user_id(user)

    await prefs.clear_preference(user_id, tool_name)
    return {"cleared": tool_name}


@router.get("/risk-info", response_model=list[ToolRiskInfo])
async def get_risk_info(
    user: ClerkUser = Depends(require_auth),
):
    """
    Get risk classification and user preference for all known tools.

    Useful for building a settings UI that shows which tools
    are auto-approved, which require approval, and which are
    permanently locked (high-risk).
    """
    redis = get_redis()
    prefs = ApprovalPreferences(redis)
    user_id = await _get_user_id(user)

    user_prefs = await prefs.get_all_preferences(user_id)

    # Gather all known tools
    from app.agents.approval import TOOL_RISK_MAP
    all_tools = set(TOOL_RISK_MAP.keys()) | HIGH_RISK_TOOLS

    results: list[ToolRiskInfo] = []
    for tool in sorted(all_tools):
        risk = classify_tool_risk(tool)
        is_high = tool in HIGH_RISK_TOOLS
        results.append(ToolRiskInfo(
            tool_name=tool,
            risk_level=risk.value,
            can_always_allow=not is_high,
            current_preference=user_prefs.get(tool),  # None = unset/default (S2)
        ))

    return results
