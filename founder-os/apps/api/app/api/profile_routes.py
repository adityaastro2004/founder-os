"""
Founder OS — User Profile Intelligence Routes
================================================
Endpoints for user profiling, business insights, and content ideas.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ClerkUser, require_auth
from app.config import get_settings
from app.database import get_db
from app.models import (
    BusinessInsight,
    ContentIdea,
    UserInsight,
    UserProfileIntel,
)

router = APIRouter(prefix="/api/profile", tags=["profile-intelligence"])


# ── Response models ────────────────────────────────────────

class ProfileOut(BaseModel):
    id: str
    user_id: str
    preferred_tone: Optional[str] = None
    communication_style: Optional[str] = None
    likes: list = []
    dislikes: list = []
    topics_of_interest: list = []
    pain_points: list = []
    expectations: list = []
    goals: list = []
    profile_summary: Optional[str] = None
    conversation_guide: Optional[str] = None
    satisfaction_score: Optional[float] = None
    total_interactions: int = 0
    positive_signals: int = 0
    negative_signals: int = 0
    version: int = 0
    last_analysis_at: Optional[str] = None
    created_at: str
    updated_at: str


class InsightOut(BaseModel):
    id: str
    agent_name: Optional[str] = None
    insight_type: str
    insight_value: str
    confidence: float = 0.8
    sentiment: Optional[str] = None
    created_at: str


class BusinessInsightOut(BaseModel):
    id: str
    insight_type: str
    title: str
    description: Optional[str] = None
    user_count: int = 0
    frequency: int = 0
    impact_score: float = 0.5
    recommended_actions: list = []
    status: str = "new"
    created_at: str


class ContentIdeaOut(BaseModel):
    id: str
    user_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    content_type: Optional[str] = None
    target_audience: Optional[str] = None
    hooks: list = []
    key_points: list = []
    source_type: Optional[str] = None
    priority: int = 5
    status: str = "new"
    created_at: str


class RebuildRequest(BaseModel):
    user_id: Optional[str] = None  # defaults to authenticated user


class AggregateRequest(BaseModel):
    pass


class ContentIdeasRequest(BaseModel):
    user_id: Optional[str] = None  # if set, personalise ideas for this user


# ── Serialisation helpers (DRY) ────────────────────────────

def _profile_to_out(profile: UserProfileIntel) -> ProfileOut:
    return ProfileOut(
        id=str(profile.id),
        user_id=profile.user_id,
        preferred_tone=profile.preferred_tone,
        communication_style=profile.communication_style,
        likes=profile.likes or [],
        dislikes=profile.dislikes or [],
        topics_of_interest=profile.topics_of_interest or [],
        pain_points=profile.pain_points or [],
        expectations=profile.expectations or [],
        goals=profile.goals or [],
        profile_summary=profile.profile_summary,
        conversation_guide=profile.conversation_guide,
        satisfaction_score=float(profile.satisfaction_score) if profile.satisfaction_score else None,
        total_interactions=profile.total_interactions or 0,
        positive_signals=profile.positive_signals or 0,
        negative_signals=profile.negative_signals or 0,
        version=profile.version or 0,
        last_analysis_at=str(profile.last_analysis_at) if profile.last_analysis_at else None,
        created_at=str(profile.created_at),
        updated_at=str(profile.updated_at),
    )


def _insight_to_out(i: UserInsight) -> InsightOut:
    return InsightOut(
        id=str(i.id),
        agent_name=i.agent_name,
        insight_type=i.insight_type,
        insight_value=i.insight_value,
        confidence=float(i.confidence) if i.confidence else 0.8,
        sentiment=i.sentiment,
        created_at=str(i.created_at),
    )


def _bi_to_out(bi: BusinessInsight) -> BusinessInsightOut:
    return BusinessInsightOut(
        id=str(bi.id),
        insight_type=bi.insight_type,
        title=bi.title,
        description=bi.description,
        user_count=bi.user_count or 0,
        frequency=bi.frequency or 0,
        impact_score=float(bi.impact_score) if bi.impact_score else 0.5,
        recommended_actions=bi.recommended_actions or [],
        status=bi.status or "new",
        created_at=str(bi.created_at),
    )


def _ci_to_out(ci: ContentIdea) -> ContentIdeaOut:
    return ContentIdeaOut(
        id=str(ci.id),
        user_id=ci.user_id,
        title=ci.title,
        description=ci.description,
        content_type=ci.content_type,
        target_audience=ci.target_audience,
        hooks=ci.hooks or [],
        key_points=ci.key_points or [],
        source_type=ci.source_type,
        priority=ci.priority or 5,
        status=ci.status or "new",
        created_at=str(ci.created_at),
    )


# ── Helper: get LLM generate callable ─────────────────────

async def _get_llm_generate(db: AsyncSession):
    """Build a simple async (system, prompt) → str callable from the registry LLM."""
    from app.agents.llm import LLMMessage, Role
    settings = get_settings()
    from app.redis import get_redis
    from app.agents.registry import AgentRegistry

    redis = get_redis()
    registry = AgentRegistry(db=db, redis=redis, settings=settings)
    llm = registry.llm_provider

    async def generate(system: str, prompt: str) -> str:
        messages = [LLMMessage(role=Role.USER, content=prompt)]
        resp = await llm.generate(messages, system=system, max_tokens=4096)
        return resp.content

    return generate


# ── Profile endpoints ─────────────────────────────────────

@router.get("/me", response_model=ProfileOut)
async def get_my_profile(
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's intelligence profile."""
    result = await db.execute(
        select(UserProfileIntel).where(UserProfileIntel.user_id == user.user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="No profile built yet. Interact with agents to build one.")
    return _profile_to_out(profile)


@router.get("/{target_user_id}", response_model=ProfileOut)
async def get_user_profile(
    target_user_id: str,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific user's profile. Only the profile owner can access it."""
    if target_user_id != user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(UserProfileIntel).where(UserProfileIntel.user_id == target_user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _profile_to_out(profile)


# ── Insights endpoints ────────────────────────────────────

@router.get("/me/insights", response_model=list[InsightOut])
async def get_my_insights(
    insight_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get insight atoms for the current user with offset pagination."""
    query = select(UserInsight).where(UserInsight.user_id == user.user_id)
    if insight_type:
        query = query.where(UserInsight.insight_type == insight_type)
    query = query.order_by(UserInsight.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    return [_insight_to_out(i) for i in result.scalars().all()]


# ── Rebuild profile ───────────────────────────────────────

@router.post("/rebuild", response_model=ProfileOut)
async def rebuild_profile(
    body: RebuildRequest,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Force a profile re-synthesis from all unprocessed insights."""
    from app.agents.profile_intelligence import ProfileIntelligence

    target_user = body.user_id or user.user_id
    if target_user != user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    llm_gen = await _get_llm_generate(db)
    pi = ProfileIntelligence(db, llm_gen)
    profile = await pi.synthesise_profile(target_user)

    if not profile:
        raise HTTPException(status_code=500, detail="Profile synthesis failed")
    return _profile_to_out(profile)


# ── Business insights ─────────────────────────────────────

@router.get("/insights/business", response_model=list[BusinessInsightOut])
async def get_business_insights(
    insight_type: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get cross-user business patterns and insights."""
    query = select(BusinessInsight)
    if insight_type:
        query = query.where(BusinessInsight.insight_type == insight_type)
    query = query.order_by(BusinessInsight.impact_score.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    return [_bi_to_out(bi) for bi in result.scalars().all()]


@router.post("/insights/business/aggregate", response_model=list[BusinessInsightOut])
async def aggregate_business_insights(
    body: AggregateRequest,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Run cross-user pattern detection to generate business insights."""
    from app.agents.profile_intelligence import ProfileIntelligence

    llm_gen = await _get_llm_generate(db)
    pi = ProfileIntelligence(db, llm_gen)
    insights = await pi.analyse_business_patterns()

    return [_bi_to_out(bi) for bi in insights]


# ── Content ideas ──────────────────────────────────────────

@router.get("/ideas/content", response_model=list[ContentIdeaOut])
async def get_content_ideas(
    status: Optional[str] = None,
    content_type: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get generated content ideas with offset pagination."""
    query = select(ContentIdea)
    if status:
        query = query.where(ContentIdea.status == status)
    if content_type:
        query = query.where(ContentIdea.content_type == content_type)
    query = query.order_by(ContentIdea.priority.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    return [_ci_to_out(ci) for ci in result.scalars().all()]


@router.post("/ideas/content/generate", response_model=list[ContentIdeaOut])
async def generate_content_ideas(
    body: ContentIdeasRequest,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Generate new content ideas from user insights and business patterns."""
    from app.agents.profile_intelligence import ProfileIntelligence

    llm_gen = await _get_llm_generate(db)
    pi = ProfileIntelligence(db, llm_gen)
    ideas = await pi.generate_content_ideas(user_id=body.user_id)

    return [_ci_to_out(ci) for ci in ideas]


# ── Stats (single query) ──────────────────────────────────

@router.get("/stats/overview")
async def get_intelligence_stats(
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Overview stats for the user intelligence system — 2 queries instead of 6."""
    # Single query for all table counts
    row = (await db.execute(text("""
        SELECT
            (SELECT COUNT(*) FROM user_profiles_intel)  AS profiles,
            (SELECT COUNT(*) FROM user_insights)         AS insights,
            (SELECT COUNT(*) FROM user_insights WHERE NOT is_processed) AS unprocessed,
            (SELECT COUNT(*) FROM business_insights)     AS biz,
            (SELECT COUNT(*) FROM content_ideas)         AS ideas
    """))).one()

    # Insight type breakdown (still needs its own query)
    type_result = await db.execute(
        select(UserInsight.insight_type, func.count().label("cnt"))
        .group_by(UserInsight.insight_type)
        .order_by(desc("cnt"))
    )
    type_breakdown = {r[0]: r[1] for r in type_result.fetchall()}

    return {
        "total_profiles": row.profiles,
        "total_insights": row.insights,
        "unprocessed_insights": row.unprocessed,
        "business_insights": row.biz,
        "content_ideas": row.ideas,
        "insight_types": type_breakdown,
    }
