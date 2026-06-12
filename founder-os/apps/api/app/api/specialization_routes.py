"""
Founder OS — Agent Specialization Routes
========================================
Founder-facing endpoints for the Agent Specialization (Evolution) Engine:
generate per-agent proposals from the founder profile, review them, and approve/
reject. Proposals are staged (``is_enabled=False``) and only go live on approval.

See docs/decisions.md ADR-003 and app/agents/specialization.py.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.specialization import SpecializationEngine
from app.api.profile_routes import _get_llm_generate  # shared (system, prompt)->str builder
from app.auth import ClerkUser, require_auth
from app.database import get_db
from app.models import Agent, User

router = APIRouter(prefix="/api/agents/specialize", tags=["agent-specialization"])


# ── Schemas ──────────────────────────────────────────────

class ProposalOut(BaseModel):
    agent_id: str
    agent_name: str
    custom_instructions: str
    tone_adjustments: str


class ApproveBody(BaseModel):
    custom_instructions: Optional[str] = Field(None, description="Edited overlay (optional)")
    tone_adjustments: Optional[str] = Field(None, description="Edited tone (optional)")


# ── Helpers ──────────────────────────────────────────────

async def _resolve_user_id(clerk_user: ClerkUser, db: AsyncSession) -> uuid.UUID:
    """Map the authenticated Clerk user to the internal users.id UUID."""
    result = await db.execute(select(User).where(User.clerk_user_id == clerk_user.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Complete onboarding before tuning agents.")
    return user.id


async def _agent_names(db: AsyncSession, agent_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not agent_ids:
        return {}
    result = await db.execute(select(Agent.id, Agent.name).where(Agent.id.in_(agent_ids)))
    return {row[0]: row[1] for row in result.all()}


# ── Routes ───────────────────────────────────────────────

@router.post("", response_model=list[ProposalOut])
async def generate_proposals(
    clerk_user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Generate (re-tune) specialization proposals for every active agent.

    Proposals are staged and NOT applied until approved.
    """
    user_id = await _resolve_user_id(clerk_user, db)
    llm_gen = await _get_llm_generate(db)  # only generate needs the LLM
    engine = SpecializationEngine(db, llm_gen)
    proposals = await engine.generate(user_id)
    return [
        ProposalOut(
            agent_id=str(p.agent_id),
            agent_name=p.agent_name,
            custom_instructions=p.custom_instructions,
            tone_adjustments=p.tone_adjustments,
        )
        for p in proposals
    ]


@router.get("/proposals", response_model=list[ProposalOut])
async def list_proposals(
    clerk_user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """List pending (not-yet-live) proposals for the founder to review."""
    user_id = await _resolve_user_id(clerk_user, db)
    engine = SpecializationEngine(db)  # no LLM needed to list
    configs = await engine.list_proposals(user_id)
    names = await _agent_names(db, [c.agent_id for c in configs])
    return [
        ProposalOut(
            agent_id=str(c.agent_id),
            agent_name=names.get(c.agent_id, "unknown"),
            custom_instructions=c.custom_instructions or "",
            tone_adjustments=c.tone_adjustments or "",
        )
        for c in configs
    ]


@router.post("/{agent_id}/approve", response_model=ProposalOut)
async def approve_proposal(
    agent_id: uuid.UUID,
    body: ApproveBody,
    clerk_user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Approve a proposal (optionally editing it) — makes it live for the founder."""
    user_id = await _resolve_user_id(clerk_user, db)
    engine = SpecializationEngine(db)  # no LLM needed to approve
    try:
        config = await engine.approve(
            user_id, agent_id, body.custom_instructions, body.tone_adjustments
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    names = await _agent_names(db, [agent_id])
    return ProposalOut(
        agent_id=str(agent_id),
        agent_name=names.get(agent_id, "unknown"),
        custom_instructions=config.custom_instructions or "",
        tone_adjustments=config.tone_adjustments or "",
    )


@router.post("/{agent_id}/reject")
async def reject_proposal(
    agent_id: uuid.UUID,
    clerk_user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Discard a staged proposal."""
    user_id = await _resolve_user_id(clerk_user, db)
    engine = SpecializationEngine(db)  # no LLM needed to reject
    removed = await engine.reject(user_id, agent_id)
    if not removed:
        raise HTTPException(status_code=404, detail="No proposal to reject for this agent.")
    return {"rejected": True, "agent_id": str(agent_id)}
