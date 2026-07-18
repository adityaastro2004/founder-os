"""
Onboarding API routes.

Handles founder profile creation during the onboarding flow.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ClerkUser, require_auth
from app.database import get_db
from app.posthog_client import get_posthog
from app.models import FounderProfile, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


async def _evolve_in_background(user_id: uuid.UUID, clerk_user_id: str) -> None:
    """After onboarding, run the Agent Evolution Engine (non-blocking): build the
    founder context model and stage regenerated agent-definition proposals.

    Opens its own DB session (the request session is already closed). Proposals are
    staged as ``proposed`` ``agent_definitions`` rows — nothing goes live without the
    founder approving via /api/agents/evolve. See ADR-006. (This is the deeper
    successor to task 001's overlay path; the /api/agents/specialize endpoints remain
    available for manual per-agent tweaks.)
    """
    from app.agents.context_model import FounderContextModelBuilder
    from app.agents.generator import AgentGenerator
    from app.api.profile_routes import _get_llm_generate
    from app.database import async_session

    try:
        async with async_session() as session:
            llm_gen = await _get_llm_generate(session)
            ctx = await FounderContextModelBuilder(session, llm_gen).build(user_id, clerk_user_id)
            if ctx is not None:
                await AgentGenerator(session, llm_gen).generate(user_id, ctx.model, ctx.version)
            await session.commit()
    except Exception:  # background work must never crash the request path
        logger.exception("Background agent evolution failed for user %s", user_id)


# ── Request / Response Schemas ───────────────────────────

class OnboardingStatusResponse(BaseModel):
    completed: bool
    profile: Optional[dict] = None


class FounderProfileCreate(BaseModel):
    """Payload from the multi-step onboarding form."""

    # Step 1: Business Info
    business_name: str = Field(..., min_length=1, max_length=255)
    business_type: str = Field(..., max_length=100)
    industry: str = Field(..., max_length=100)
    target_audience: str = ""

    # Step 2: Stage & Goals
    business_stage: str = Field(..., max_length=100)
    primary_goal: str = Field(..., max_length=100)
    team_size: int = Field(default=1, ge=1)
    team_roles: list[str] = Field(default_factory=list)

    # Step 3: Metrics
    current_mrr: float = 0.0
    current_users: int = 0
    monthly_traffic: int = 0

    # Step 4: Preferences
    working_hours: Optional[dict] = None
    preferred_communication: str = "email"
    writing_voice: str = ""


class FounderProfileResponse(BaseModel):
    id: str
    business_name: str | None
    business_type: str | None
    business_stage: str | None
    industry: str | None
    target_audience: str | None
    primary_goal: str | None
    team_size: int
    current_mrr: float | None
    current_users: int | None
    monthly_traffic: int | None
    preferred_communication: str | None
    writing_voice: str | None


# ── Helpers ──────────────────────────────────────────────

async def _get_or_create_user(
    clerk_user: ClerkUser, db: AsyncSession
) -> User:
    """Ensure a User row exists for this Clerk user; return it."""
    result = await db.execute(
        select(User).where(User.clerk_user_id == clerk_user.user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            clerk_user_id=clerk_user.user_id,
            email=clerk_user.email or f"{clerk_user.user_id}@placeholder.local",
            full_name=clerk_user.claims.get("name"),
            avatar_url=clerk_user.claims.get("image_url"),
        )
        db.add(user)
        await db.flush()

    return user


# ── Routes ───────────────────────────────────────────────

@router.get("/status", response_model=OnboardingStatusResponse)
async def onboarding_status(
    clerk_user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Check whether the authenticated user has completed onboarding."""
    result = await db.execute(
        select(User).where(User.clerk_user_id == clerk_user.user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        return OnboardingStatusResponse(completed=False)

    result = await db.execute(
        select(FounderProfile).where(FounderProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        return OnboardingStatusResponse(completed=False)

    return OnboardingStatusResponse(
        completed=True,
        profile={
            "business_name": profile.business_name,
            "business_type": profile.business_type,
            "business_stage": profile.business_stage,
        },
    )


@router.post("/profile", response_model=FounderProfileResponse)
async def create_founder_profile(
    payload: FounderProfileCreate,
    background_tasks: BackgroundTasks,
    clerk_user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Create or update the founder profile (onboarding completion)."""
    user = await _get_or_create_user(clerk_user, db)

    # Check for existing profile
    result = await db.execute(
        select(FounderProfile).where(FounderProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()

    if profile:
        # Update existing
        for field_name, value in payload.model_dump().items():
            setattr(profile, field_name, value)
    else:
        # Create new
        profile = FounderProfile(
            user_id=user.id,
            **payload.model_dump(),
        )
        db.add(profile)

    await db.flush()

    # Run the Agent Evolution Engine (non-blocking; ADR-006): build the context model
    # and stage regenerated agent-definition proposals. Runs after the response is sent
    # and the request session has committed.
    background_tasks.add_task(_evolve_in_background, user.id, clerk_user.user_id)

    ph = get_posthog()
    if ph is not None:
        ph.capture(
            distinct_id=clerk_user.user_id,
            event="onboarding_completed",
            properties={
                "business_type": payload.business_type,
                "industry": payload.industry,
                "business_stage": payload.business_stage,
                "primary_goal": payload.primary_goal,
                "team_size": payload.team_size,
                "preferred_communication": payload.preferred_communication,
            },
        )

    return FounderProfileResponse(
        id=str(profile.id),
        business_name=profile.business_name,
        business_type=profile.business_type,
        business_stage=profile.business_stage,
        industry=profile.industry,
        target_audience=profile.target_audience,
        primary_goal=profile.primary_goal,
        team_size=profile.team_size,
        current_mrr=float(profile.current_mrr) if profile.current_mrr else None,
        current_users=profile.current_users,
        monthly_traffic=profile.monthly_traffic,
        preferred_communication=profile.preferred_communication,
        writing_voice=profile.writing_voice,
    )
