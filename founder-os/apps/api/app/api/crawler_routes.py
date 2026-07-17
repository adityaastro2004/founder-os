"""
Founder OS — Research/Crawler API Routes
==========================================
REST endpoints for the web crawler & research engine.

Endpoints:
  POST /api/research/run          — Trigger a full research cycle
  GET  /api/research/status        — Get last research run status
  GET  /api/research/findings      — List recent findings (paginated)
  POST /api/research/competitors   — Add/update competitor list
  GET  /api/research/competitors   — Get tracked competitors
  POST /api/research/sources       — Add custom RSS/URL sources
  GET  /api/research/profile       — Get the auto-generated research profile
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ClerkUser, require_auth
from app.crawler.engine import get_crawler_engine
from app.crawler.research import (
    ResearchProfile,
    CompetitorUpdate,
    TrendItem,
    CustomerSignal,
    ResearchReport,
    get_research_engine,
)
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["research"])


# ============================================================================
# Request/Response Models
# ============================================================================

class RunResearchRequest(BaseModel):
    """Request to trigger a research cycle.

    Note: the target user is ALWAYS the authenticated caller. There is
    deliberately no `user_id` field — accepting one would let a caller run a
    research cycle scoped to another user's data (IDOR). See standards/security.md.
    """
    pass


class ResearchStatusResponse(BaseModel):
    """Status of last research run."""
    last_run_at: Optional[datetime]
    findings_count: int
    competitor_updates_count: int
    status: str  # "idle", "running", "completed", "failed"


class ResearchFindingResponse(BaseModel):
    """A stored research finding."""
    id: str
    title: str
    summary: str
    category: str
    source_url: str
    relevance_score: float
    created_at: datetime


class ResearchProfileResponse(BaseModel):
    """Founder's auto-generated research profile."""
    company_name: str
    industry: str
    competitors: list[str]
    technologies: list[str]
    keywords: list[str]
    target_audience: str
    active_goals: list[str]
    recent_topics: list[str]


class CompetitorListRequest(BaseModel):
    """Add or update tracked competitors."""
    competitors: list[str] = Field(..., description="List of competitor names")
    action: str = Field("set", description="'set' to replace, 'add' to append")


class CompetitorListResponse(BaseModel):
    """Current tracked competitors."""
    competitors: list[str]


class ResearchSourceRequest(BaseModel):
    """Add a custom RSS or URL source."""
    name: str = Field(..., description="Source name")
    rss_url: Optional[str] = Field(None, description="RSS feed URL")
    website_url: Optional[str] = Field(None, description="Website URL")
    source_type: str = Field("news", description="news, community, launches, insights")


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/run")
async def trigger_research_cycle(
    request: RunResearchRequest,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Trigger a full research cycle for the user.

    Returns:
      - findings_stored: number of findings saved
      - queries_executed: number of search queries run
      - pages_crawled: number of pages visited
      - competitor_updates: list of competitor findings
      - trends: list of industry trend findings
      - customer_signals: list of customer sentiment findings
    """
    try:
        # Identity is always the verified caller — never a body-supplied id.
        user_id = user.user_id

        # Initialize research engine
        crawl_engine = get_crawler_engine()
        research_engine = get_research_engine(crawl_engine)

        # Run research cycle
        report = await research_engine.run_research_cycle(user_id)

        if not report:
            raise HTTPException(status_code=500, detail="Research cycle failed")

        return {
            "success": True,
            "generated_at": report.generated_at,
            "findings_stored": report.findings_stored,
            "queries_executed": report.queries_executed,
            "pages_crawled": report.pages_crawled,
            "competitor_updates_count": len(report.competitor_updates),
            "trends_count": len(report.trends),
            "customer_signals_count": len(report.customer_signals),
            "competitor_updates": [
                {
                    "competitor": u.competitor,
                    "title": u.title,
                    "summary": u.summary,
                    "source_url": u.source_url,
                    "change_type": u.change_type,
                }
                for u in report.competitor_updates[:5]
            ],
            "trends": [
                {
                    "topic": t.topic,
                    "summary": t.summary,
                    "relevance": t.relevance,
                }
                for t in report.trends[:5]
            ],
            "customer_signals": [
                {
                    "topic": c.topic,
                    "sentiment": c.sentiment,
                    "summary": c.summary,
                    "platform": c.platform,
                }
                for c in report.customer_signals[:5]
            ],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("trigger_research_cycle failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_research_status(
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> ResearchStatusResponse:
    """
    Get the status of the last research run.
    Returns count of findings, last run time, etc.
    """
    try:
        user_id = user.user_id

        # Query for recent research findings
        result = await db.execute(
            sa_text(
                """
                SELECT COUNT(*) as count, MAX(created_at) as last_run
                FROM memory_pages
                WHERE user_id = :uid AND source = 'crawler'
                """
            ),
            {"uid": user_id},
        )
        row = result.first()

        findings_count = row[0] if row else 0
        last_run_at = row[1] if row and row[1] else None

        return ResearchStatusResponse(
            last_run_at=last_run_at,
            findings_count=findings_count,
            competitor_updates_count=0,  # Could query more specifically
            status="completed" if last_run_at else "idle",
        )

    except Exception as e:
        logger.error("get_research_status failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/findings")
async def list_research_findings(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    category: Optional[str] = Query(None, description="Filter by category"),
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    List recent research findings, paginated.
    Optionally filter by category (competitor, trend, customer, etc.)
    """
    try:
        user_id = user.user_id

        # Build query
        where_clause = "WHERE user_id = :uid AND source = 'crawler'"
        params = {"uid": user_id}

        if category:
            where_clause += " AND metadata_->>'category' = :cat"
            params["cat"] = category

        # Get total count
        count_result = await db.execute(
            sa_text(f"SELECT COUNT(*) FROM memory_pages {where_clause}"),
            params,
        )
        total = count_result.scalar()

        # Get paginated results
        result = await db.execute(
            sa_text(
                f"""
                SELECT id, title, summary, metadata_, created_at
                FROM memory_pages
                {where_clause}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :skip
                """
            ),
            {**params, "limit": limit, "skip": skip},
        )

        findings = []
        for row in result:
            metadata = row[4] or {}
            findings.append(
                {
                    "id": str(row[0]),
                    "title": row[1],
                    "summary": row[2],
                    "category": metadata.get("category", "unknown"),
                    "source_url": metadata.get("source_url", ""),
                    "relevance_score": metadata.get("relevance_score", 0.5),
                    "created_at": row[5],
                }
            )

        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "findings": findings,
        }

    except Exception as e:
        logger.error("list_research_findings failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profile")
async def get_research_profile(
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> ResearchProfileResponse:
    """
    Get the auto-generated research profile for the user.
    Built from planner_users and recent memory_pages.
    """
    try:
        user_id = user.user_id

        # Initialize research engine
        crawl_engine = get_crawler_engine()
        research_engine = get_research_engine(crawl_engine)

        # Build profile
        profile = await research_engine.build_research_profile(user_id)

        if not profile:
            raise HTTPException(
                status_code=404, detail="Could not build research profile"
            )

        return ResearchProfileResponse(
            company_name=profile.company_name,
            industry=profile.industry,
            competitors=profile.competitors,
            technologies=profile.technologies,
            keywords=profile.keywords,
            target_audience=profile.target_audience,
            active_goals=profile.active_goals,
            recent_topics=profile.recent_topics,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_research_profile failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/competitors")
async def update_tracked_competitors(
    request: CompetitorListRequest,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> CompetitorListResponse:
    """
    Add or replace the list of tracked competitors.
    Stores in planner_users or a separate table.
    """
    try:
        user_id = user.user_id

        # For now, store in memory_pages as a special record
        # In production, might add a dedicated competitors table
        if request.action == "set":
            # Mark old competitors list as inactive
            await db.execute(
                sa_text(
                    """
                    UPDATE memory_pages
                    SET is_active = false
                    WHERE user_id = :uid AND chapter = 'research' AND title LIKE 'Tracked Competitors%'
                    """
                ),
                {"uid": user_id},
            )

        # Store new competitors list as memory
        from app.memory.manager import get_memory_manager
        memory_manager = get_memory_manager()

        await memory_manager.async_store(
            user_id=user_id,
            title="Tracked Competitors",
            content=", ".join(request.competitors),
            page_type="note",
            importance=0.8,
            chapter="research",
            tags=["competitors", "tracking"],
            source="crawler",
            auto_embed=False,
        )

        return CompetitorListResponse(competitors=request.competitors)

    except Exception as e:
        logger.error("update_tracked_competitors failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/competitors")
async def get_tracked_competitors(
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> CompetitorListResponse:
    """
    Get the current list of tracked competitors.
    """
    try:
        user_id = user.user_id

        # Query for the latest competitors list
        result = await db.execute(
            sa_text(
                """
                SELECT content
                FROM memory_pages
                WHERE user_id = :uid AND title = 'Tracked Competitors' AND is_active = true
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"uid": user_id},
        )

        row = result.first()
        if row:
            competitors = [c.strip() for c in row[0].split(",") if c.strip()]
        else:
            competitors = []

        return CompetitorListResponse(competitors=competitors)

    except Exception as e:
        logger.error("get_tracked_competitors failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sources")
async def add_custom_source(
    request: ResearchSourceRequest,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Add a custom RSS or website source for monitoring.
    Stored in memory_pages for now.
    """
    try:
        user_id = user.user_id

        # Store source as memory
        from app.memory.manager import get_memory_manager
        memory_manager = get_memory_manager()

        source_info = {
            "name": request.name,
            "rss_url": request.rss_url,
            "website_url": request.website_url,
            "type": request.source_type,
        }

        await memory_manager.async_store(
            user_id=user_id,
            title=f"Custom Research Source: {request.name}",
            content=str(source_info),
            page_type="note",
            importance=0.6,
            chapter="research",
            tags=["custom_source", request.source_type],
            entities={"sources": [request.name]},
            source="crawler",
            auto_embed=False,
        )

        return {
            "success": True,
            "message": f"Added source: {request.name}",
            "source": source_info,
        }

    except Exception as e:
        logger.error("add_custom_source failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
