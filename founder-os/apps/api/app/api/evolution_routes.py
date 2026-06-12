"""
Founder OS — Agent Evolution Routes (task 003).
===============================================
Founder-facing endpoints for the Agent Evolution Engine: build the Founder Context
Model, regenerate agent definitions from it, and review/approve/reject/rollback the
proposals. Regenerations are staged (``proposed``) and only go live on approval.

See docs/agent-evolution.md, docs/decisions.md ADR-006,
app/agents/context_model.py, app/agents/generator.py.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context_model import FounderContextModelBuilder
from app.agents.generator import AgentGenerator
from app.api.profile_routes import _get_llm_generate  # shared (system, prompt)->str builder
from app.auth import ClerkUser, require_auth
from app.database import get_db
from app.models import AgentDefinition, User

router = APIRouter(prefix="/api/agents/evolve", tags=["agent-evolution"])


# ── Schemas ──────────────────────────────────────────────

class DefinitionProposalOut(BaseModel):
    agent_name: str
    version: int
    system_prompt: str
    decision_framework: str = ""
    selected_tools: list[str] = []
    status: str = "proposed"


class ContextModelOut(BaseModel):
    version: int
    model: dict
    changed: bool = False


class ApproveBody(BaseModel):
    system_prompt: Optional[str] = Field(None, description="Edited system prompt (optional)")
    decision_framework: Optional[str] = Field(None, description="Edited decision framework (optional)")
    selected_tools: Optional[list[str]] = Field(None, description="Edited tool selection (optional)")


# ── Helpers ──────────────────────────────────────────────

async def _resolve_user(clerk_user: ClerkUser, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.clerk_user_id == clerk_user.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Complete onboarding before evolving agents.")
    return user


def _proposal_out(d: AgentDefinition) -> DefinitionProposalOut:
    return DefinitionProposalOut(
        agent_name=d.agent_name,
        version=d.version,
        system_prompt=d.system_prompt,
        decision_framework=d.decision_framework or "",
        selected_tools=list(d.selected_tools or []),
        status=d.status,
    )


# ── Routes ───────────────────────────────────────────────

@router.post("", response_model=list[DefinitionProposalOut])
async def evolve(
    clerk_user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Build/refresh the founder context model and regenerate agent definition proposals.

    Proposals are staged and NOT applied until approved.
    """
    user = await _resolve_user(clerk_user, db)
    llm_gen = await _get_llm_generate(db)

    ctx = await FounderContextModelBuilder(db, llm_gen).build(user.id, clerk_user.user_id)
    if ctx is None:
        raise HTTPException(status_code=400, detail="No founder profile to build a context model from.")

    proposals = await AgentGenerator(db, llm_gen).generate(user.id, ctx.model, ctx.version)
    return [
        DefinitionProposalOut(
            agent_name=p.agent_name,
            version=p.version,
            system_prompt=p.system_prompt,
            decision_framework=p.decision_framework,
            selected_tools=p.selected_tools,
        )
        for p in proposals
    ]


@router.get("/context-model", response_model=ContextModelOut)
async def get_context_model(
    clerk_user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Return the founder's current structured context model."""
    user = await _resolve_user(clerk_user, db)
    latest = await FounderContextModelBuilder(db, await _get_llm_generate(db)).latest(user.id)
    if latest is None:
        raise HTTPException(status_code=404, detail="No context model built yet.")
    return ContextModelOut(version=latest.version, model=latest.model)


@router.get("/proposals", response_model=list[DefinitionProposalOut])
async def list_proposals(
    clerk_user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """List pending (not-yet-active) agent definition proposals."""
    user = await _resolve_user(clerk_user, db)
    proposals = await AgentGenerator(db).list_proposals(user.id)  # no LLM needed to list
    return [_proposal_out(d) for d in proposals]


@router.post("/{agent_name}/approve", response_model=DefinitionProposalOut)
async def approve(
    agent_name: str,
    body: ApproveBody,
    clerk_user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Approve a proposed definition (optionally with edits) — makes it the active
    definition for this founder, superseding any prior active one."""
    user = await _resolve_user(clerk_user, db)
    try:
        row = await AgentGenerator(db).approve(
            user.id, agent_name, body.system_prompt, body.decision_framework, body.selected_tools
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _proposal_out(row)


@router.post("/{agent_name}/reject")
async def reject(
    agent_name: str,
    clerk_user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Discard a pending proposal."""
    user = await _resolve_user(clerk_user, db)
    removed = await AgentGenerator(db).reject(user.id, agent_name)
    if not removed:
        raise HTTPException(status_code=404, detail="No proposal to reject for this agent.")
    return {"rejected": True, "agent_name": agent_name}


@router.post("/{agent_name}/rollback", response_model=Optional[DefinitionProposalOut])
async def rollback(
    agent_name: str,
    clerk_user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Revert to the previous version (or the global default if none remain)."""
    user = await _resolve_user(clerk_user, db)
    prior = await AgentGenerator(db).rollback(user.id, agent_name)
    return _proposal_out(prior) if prior is not None else None
