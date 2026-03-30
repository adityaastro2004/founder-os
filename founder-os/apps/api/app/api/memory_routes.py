"""
Founder OS — Memory API Routes
==================================
REST endpoints for the temporal memory system.

Endpoints:
  POST /api/memory/store         — Add a memory
  POST /api/memory/recall        — Composite-scored recall
  GET  /api/memory/reviews       — Memories due for review
  POST /api/memory/review/{id}   — Mark a memory as reviewed
  GET  /api/memory/chapters      — List all chapters
  GET  /api/memory/chapter/{ch}  — Browse a chapter
  POST /api/memory/search/entity — Search by entity
  POST /api/memory/link          — Link two memories
  GET  /api/memory/links/{id}    — Get linked memories
  GET  /api/memory/stats         — Memory system stats
  POST /api/memory/pin/{id}      — Pin/unpin a memory
  DELETE /api/memory/{id}        — Soft-delete a memory
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import require_auth, ClerkUser
from app.memory.manager import get_memory_manager, MemoryHit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memory", tags=["memory"])


# ============================================================================
# Request / Response models
# ============================================================================

class StoreRequest(BaseModel):
    user_id: str = Field("default-user")
    title: str = Field(..., min_length=1, description="What happened / what to remember")
    content: str = Field(..., min_length=1, description="Full details")
    page_type: str = Field("event", description="event, decision, milestone, metric, insight, note")
    importance: float = Field(0.5, ge=0, le=1, description="How important (0-1)")
    decay_rate: float = Field(0.001, ge=0, description="How fast it fades (0=never)")
    chapter: Optional[str] = Field(None, description="product, hiring, fundraising, marketing, ops, etc.")
    tags: list[str] = Field(default_factory=list)
    entities: dict = Field(default_factory=dict, description='{"people": [...], "companies": [...], "tools": [...]}')
    summary: Optional[str] = None
    source: str = Field("user_input")
    is_pinned: bool = False
    review_in_days: Optional[int] = Field(None, description="Schedule a review in N days")
    occurred_at: Optional[str] = Field(None, description="ISO datetime — when it happened (default: now)")
    parent_id: Optional[str] = Field(None, description="UUID of parent memory page")
    metadata: dict = Field(default_factory=dict)


class RecallRequest(BaseModel):
    user_id: str = Field("default-user")
    query: Optional[str] = Field(None, description="Natural language query (will be embedded)")
    limit: int = Field(10, ge=1, le=100)
    chapter: Optional[str] = None
    page_type: Optional[str] = None
    tags: Optional[list[str]] = None
    min_importance: float = Field(0.0, ge=0, le=1)
    since: Optional[str] = Field(None, description="ISO datetime — only memories after this time")
    until: Optional[str] = Field(None, description="ISO datetime — only memories before this time")


class LinkRequest(BaseModel):
    source_id: str = Field(..., description="UUID of source memory")
    target_id: str = Field(..., description="UUID of target memory")
    link_type: str = Field("related", description="related, caused_by, led_to, contradicts, updates, supersedes, part_of")
    strength: float = Field(0.5, ge=0, le=1)
    metadata: dict = Field(default_factory=dict)


class EntitySearchRequest(BaseModel):
    user_id: str = Field("default-user")
    entity: str = Field(..., min_length=1, description="Person, company, or tool name")
    limit: int = Field(20, ge=1, le=100)


# ============================================================================
# Helper
# ============================================================================

def _hit_to_dict(h: MemoryHit) -> dict:
    return {
        "id": str(h.id),
        "title": h.title,
        "content": h.content,
        "summary": h.summary,
        "page_type": h.page_type,
        "chapter": h.chapter,
        "tags": h.tags,
        "entities": h.entities,
        "occurred_at": h.occurred_at.isoformat() if h.occurred_at else None,
        "importance": h.importance,
        "is_pinned": h.is_pinned,
        "source": h.source,
        "scores": {
            "composite": h.composite_score,
            "semantic": h.semantic_score,
            "temporal": h.temporal_score,
            "importance": h.importance_score,
            "access": h.access_score,
        },
    }


# ============================================================================
# STORE
# ============================================================================

@router.post("/store")
async def store_memory(body: StoreRequest, user: ClerkUser = Depends(require_auth)):
    """Store a new memory page in the temporal knowledge graph."""
    mgr = get_memory_manager()

    occurred = None
    if body.occurred_at:
        try:
            occurred = datetime.fromisoformat(body.occurred_at)
        except ValueError:
            raise HTTPException(400, "Invalid occurred_at datetime format")

    parent = None
    if body.parent_id:
        try:
            parent = uuid.UUID(body.parent_id)
        except ValueError:
            raise HTTPException(400, "Invalid parent_id UUID")

    page_id = await mgr.async_store(
        user_id=user.user_id,
        title=body.title,
        content=body.content,
        page_type=body.page_type,
        occurred_at=occurred,
        importance=body.importance,
        decay_rate=body.decay_rate,
        chapter=body.chapter,
        tags=body.tags,
        entities=body.entities,
        summary=body.summary,
        source=body.source,
        is_pinned=body.is_pinned,
        review_in_days=body.review_in_days,
        parent_id=parent,
        metadata=body.metadata,
    )

    return {
        "status": "stored",
        "page_id": str(page_id),
        "title": body.title,
        "chapter": body.chapter,
        "message": f"Memory '{body.title}' stored in temporal knowledge graph.",
    }


# ============================================================================
# RECALL
# ============================================================================

@router.post("/recall")
async def recall_memories(body: RecallRequest, user: ClerkUser = Depends(require_auth)):
    """
    Retrieve memories using composite scoring:
    score = semantic_similarity × w1 + temporal_relevance × w2 + importance × w3 + access_freq × w4
    """
    mgr = get_memory_manager()

    since = None
    until = None
    if body.since:
        try:
            since = datetime.fromisoformat(body.since)
        except ValueError:
            raise HTTPException(400, "Invalid 'since' datetime")
    if body.until:
        try:
            until = datetime.fromisoformat(body.until)
        except ValueError:
            raise HTTPException(400, "Invalid 'until' datetime")

    hits = await mgr.async_recall(
        user_id=user.user_id,
        query=body.query,
        limit=body.limit,
        chapter=body.chapter,
        page_type=body.page_type,
        tags=body.tags,
        min_importance=body.min_importance,
        since=since,
        until=until,
    )

    return {
        "user_id": user.user_id,
        "query": body.query,
        "total_results": len(hits),
        "memories": [_hit_to_dict(h) for h in hits],
    }


# ============================================================================
# REVIEWS
# ============================================================================

@router.get("/reviews")
async def get_reviews(user: ClerkUser = Depends(require_auth), limit: int = 20):
    """Get memories due for review (spaced-repetition)."""
    mgr = get_memory_manager()
    hits = await mgr.async_get_due_reviews(user.user_id, limit)
    return {
        "user_id": user.user_id,
        "reviews_due": len(hits),
        "memories": [_hit_to_dict(h) for h in hits],
    }


@router.post("/review/{page_id}")
async def mark_reviewed(page_id: str, user: ClerkUser = Depends(require_auth)):
    """Mark a memory as reviewed — advances the review schedule."""
    mgr = get_memory_manager()
    try:
        pid = uuid.UUID(page_id)
    except ValueError:
        raise HTTPException(400, "Invalid page_id UUID")

    await mgr.async_mark_reviewed(pid)
    return {"status": "reviewed", "page_id": page_id}


# ============================================================================
# CHAPTERS
# ============================================================================

@router.get("/chapters")
async def list_chapters(user: ClerkUser = Depends(require_auth)):
    """List all memory chapters with counts."""
    mgr = get_memory_manager()
    chapters = await mgr.async_list_chapters(user.user_id)
    return {"user_id": user.user_id, "chapters": chapters}


@router.get("/chapter/{chapter}")
async def browse_chapter(
    chapter: str,
    user: ClerkUser = Depends(require_auth),
    limit: int = 50,
    offset: int = 0,
    order: str = Query("desc", pattern="^(asc|desc)$"),
):
    """Browse memories within a chapter, ordered chronologically."""
    mgr = get_memory_manager()
    hits = await mgr.async_browse_chapter(user.user_id, chapter, limit=limit, offset=offset, order=order)
    return {
        "user_id": user.user_id,
        "chapter": chapter,
        "count": len(hits),
        "memories": [_hit_to_dict(h) for h in hits],
    }


# ============================================================================
# ENTITY SEARCH
# ============================================================================

@router.post("/search/entity")
async def search_entities(body: EntitySearchRequest, user: ClerkUser = Depends(require_auth)):
    """Find memories mentioning a specific entity (person, company, tool)."""
    mgr = get_memory_manager()
    hits = await mgr.async_search_entities(user.user_id, body.entity, limit=body.limit)
    return {
        "user_id": user.user_id,
        "entity": body.entity,
        "total_results": len(hits),
        "memories": [_hit_to_dict(h) for h in hits],
    }


# ============================================================================
# LINKS
# ============================================================================

@router.post("/link")
async def link_memories(body: LinkRequest, user: ClerkUser = Depends(require_auth)):
    """Create a typed link between two memory pages."""
    mgr = get_memory_manager()
    try:
        src = uuid.UUID(body.source_id)
        tgt = uuid.UUID(body.target_id)
    except ValueError:
        raise HTTPException(400, "Invalid UUID")

    link_id = await mgr.async_link(src, tgt, body.link_type, body.strength, body.metadata)
    return {
        "status": "linked",
        "link_id": str(link_id),
        "link_type": body.link_type,
    }


@router.get("/links/{page_id}")
async def get_links(
    page_id: str,
    user: ClerkUser = Depends(require_auth),
    link_type: Optional[str] = None,
    direction: str = Query("both", pattern="^(both|incoming|outgoing)$"),
):
    """Get all memories linked to a given page."""
    mgr = get_memory_manager()
    try:
        pid = uuid.UUID(page_id)
    except ValueError:
        raise HTTPException(400, "Invalid page_id UUID")

    links = await mgr.async_get_linked(pid, link_type=link_type, direction=direction)
    return {"page_id": page_id, "links": links}


# ============================================================================
# STATS
# ============================================================================

@router.get("/stats")
async def memory_stats(user: ClerkUser = Depends(require_auth)):
    """Memory system stats for a user."""
    mgr = get_memory_manager()
    stats = await mgr.async_stats(user.user_id)
    return {"user_id": user.user_id, **stats}


# ============================================================================
# PIN / UNPIN
# ============================================================================

@router.post("/pin/{page_id}")
async def pin_memory(page_id: str, user: ClerkUser = Depends(require_auth), pin: bool = Query(True)):
    """Pin a memory (pinned = never decays, always top-ranked)."""
    mgr = get_memory_manager()
    try:
        pid = uuid.UUID(page_id)
    except ValueError:
        raise HTTPException(400, "Invalid page_id UUID")

    ok = await mgr.async_pin(pid, pin)
    if not ok:
        raise HTTPException(404, "Memory not found")
    return {"status": "pinned" if pin else "unpinned", "page_id": page_id}


# ============================================================================
# DELETE (soft)
# ============================================================================

@router.delete("/{page_id}")
async def delete_memory(page_id: str, user: ClerkUser = Depends(require_auth)):
    """Soft-delete a memory page."""
    mgr = get_memory_manager()
    try:
        pid = uuid.UUID(page_id)
    except ValueError:
        raise HTTPException(400, "Invalid page_id UUID")

    ok = await mgr.async_delete(pid)
    if not ok:
        raise HTTPException(404, "Memory not found")
    return {"status": "deleted", "page_id": page_id}
