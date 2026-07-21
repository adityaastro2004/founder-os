"""
Global search routes — unified cross-entity search for the ⌘K command palette.

One read-only endpoint that matches the founder's tasks, knowledge items,
content ideas, and automations (workflows) by substring. The frontend owns
grouping, ordering across groups, and building hrefs — this stays UI-agnostic.

Deliberately NOT here (see tasks/024): chat-message search (sessions aren't
addressable in the UI yet) and semantic/pgvector search (the knowledge page
owns the embedder path; the palette deep-links into it instead).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ClerkUser, require_auth
from app.database import get_db
from app.models import ContentIdea, KnowledgeItem, Task, Workflow
from app.posthog_client import get_posthog
from app.users import get_or_create_user_id

router = APIRouter(prefix="/api/search", tags=["search"])

# Bounded per entity so the endpoint stays palette-fast regardless of `limit`.
_PER_TYPE_MAX = 8
_SNIPPET_LEN = 140


class SearchResult(BaseModel):
    type: Literal["task", "knowledge", "content_idea", "workflow"]
    id: str
    title: str
    snippet: Optional[str] = None
    meta: Optional[str] = None
    updated_at: Optional[datetime] = None


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchResult]


def _escape_like(q: str) -> str:
    """Escape LIKE wildcards so user input matches literally."""
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _snippet(text: Optional[str], q: str) -> Optional[str]:
    """A ~140-char window around the first case-insensitive match of ``q``."""
    if not text:
        return None
    text = " ".join(text.split())  # collapse newlines/runs of whitespace
    pos = text.lower().find(q.lower())
    if pos == -1:
        return text[:_SNIPPET_LEN] + ("…" if len(text) > _SNIPPET_LEN else "")
    start = max(0, pos - 40)
    end = min(len(text), start + _SNIPPET_LEN)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


@router.get("", response_model=SearchResponse)
async def global_search(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(20, ge=1, le=32),
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """
    Substring search across the founder's tasks, knowledge, content ideas, and
    automations. Title matches sort before body matches within each type;
    newest first as a tiebreak.
    """
    q = q.strip()
    if not q:
        return SearchResponse(query=q, total=0, results=[])

    uid = await get_or_create_user_id(user.user_id, db, email=user.email)
    pattern = f"%{_escape_like(q)}%"
    per_type = max(1, min(_PER_TYPE_MAX, limit // 4))
    results: list[SearchResult] = []

    def _title_first(title_col):
        # boolean desc → rows whose TITLE matched sort above body-only matches
        return title_col.ilike(pattern, escape="\\").desc()

    tasks = (
        await db.execute(
            select(Task.id, Task.title, Task.description, Task.status, Task.updated_at)
            .where(
                Task.user_id == uid,
                or_(
                    Task.title.ilike(pattern, escape="\\"),
                    Task.description.ilike(pattern, escape="\\"),
                ),
            )
            .order_by(_title_first(Task.title), Task.updated_at.desc())
            .limit(per_type)
        )
    ).all()
    results += [
        SearchResult(
            type="task",
            id=str(r.id),
            title=r.title,
            snippet=_snippet(r.description, q),
            meta=r.status,
            updated_at=r.updated_at,
        )
        for r in tasks
    ]

    knowledge = (
        await db.execute(
            select(
                KnowledgeItem.id,
                KnowledgeItem.title,
                KnowledgeItem.content,
                KnowledgeItem.category,
                KnowledgeItem.updated_at,
            )
            .where(
                KnowledgeItem.user_id == uid,
                KnowledgeItem.is_active.is_(True),
                or_(
                    KnowledgeItem.title.ilike(pattern, escape="\\"),
                    KnowledgeItem.content.ilike(pattern, escape="\\"),
                ),
            )
            .order_by(_title_first(KnowledgeItem.title), KnowledgeItem.updated_at.desc())
            .limit(per_type)
        )
    ).all()
    results += [
        SearchResult(
            type="knowledge",
            id=str(r.id),
            title=r.title or "Untitled document",
            snippet=_snippet(r.content, q),
            meta=r.category,
            updated_at=r.updated_at,
        )
        for r in knowledge
    ]

    # content_ideas.user_id is the Clerk string id, not the users.id UUID.
    ideas = (
        await db.execute(
            select(
                ContentIdea.id,
                ContentIdea.title,
                ContentIdea.description,
                ContentIdea.status,
                ContentIdea.updated_at,
            )
            .where(
                ContentIdea.user_id == user.user_id,
                or_(
                    ContentIdea.title.ilike(pattern, escape="\\"),
                    ContentIdea.description.ilike(pattern, escape="\\"),
                ),
            )
            .order_by(_title_first(ContentIdea.title), ContentIdea.updated_at.desc())
            .limit(per_type)
        )
    ).all()
    results += [
        SearchResult(
            type="content_idea",
            id=str(r.id),
            title=r.title,
            snippet=_snippet(r.description, q),
            meta=r.status,
            updated_at=r.updated_at,
        )
        for r in ideas
    ]

    workflows = (
        await db.execute(
            select(
                Workflow.id,
                Workflow.name,
                Workflow.description,
                Workflow.is_active,
                Workflow.updated_at,
            )
            .where(
                Workflow.user_id == uid,
                or_(
                    Workflow.name.ilike(pattern, escape="\\"),
                    Workflow.description.ilike(pattern, escape="\\"),
                ),
            )
            .order_by(_title_first(Workflow.name), Workflow.updated_at.desc())
            .limit(per_type)
        )
    ).all()
    results += [
        SearchResult(
            type="workflow",
            id=str(r.id),
            title=r.name,
            snippet=_snippet(r.description, q),
            meta="active" if r.is_active else "paused",
            updated_at=r.updated_at,
        )
        for r in workflows
    ]

    ph = get_posthog()
    if ph is not None:
        ph.capture(
            distinct_id=user.user_id,
            event="global_searched",
            properties={
                "results_count": len(results),
                "has_results": len(results) > 0,
            },
        )

    return SearchResponse(query=q, total=len(results), results=results)
