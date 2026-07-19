"""
Founder OS — Temporal Memory Manager
========================================
Page-indexed, temporally-aware long-term memory for startup founders.

Instead of pure vector similarity search, uses a **composite scoring** system:

  score = (semantic_sim × w_sem)
        + (temporal_relevance × w_temp)
        + (importance × w_imp)
        + (access_boost × w_acc)

Where:
  temporal_relevance = importance × exp(-decay_rate × days_since_occurred)

Features:
  - Store / Recall / Review lifecycle
  - Spaced-repetition review scheduling
  - Chapter-based browsing (product, hiring, fundraising …)
  - Entity tracking (people, companies, tools)
  - Typed links between memories (caused_by, updates, supersedes …)
  - Both sync + async interfaces (scheduler = sync, routes = async)
  - Hooks into the existing Ollama/OpenAI embedding provider
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
from app.log_sanitize import sl

logger = logging.getLogger(__name__)

# ── Scoring weight defaults ─────────────────────────────────────
DEFAULT_WEIGHTS = {
    "semantic": 0.35,
    "temporal": 0.30,
    "importance": 0.20,
    "access": 0.15,
}

# ── Spaced-repetition review intervals (Leitner-like) ───────────
REVIEW_INTERVALS = [1, 3, 7, 14, 30, 60, 120, 240]  # days


@dataclass
class MemoryHit:
    """A single recall result with composite scoring breakdown."""
    id: uuid.UUID
    title: str
    content: str
    summary: str | None
    page_type: str
    chapter: str | None
    tags: list[str]
    entities: dict
    occurred_at: datetime
    importance: float
    composite_score: float
    semantic_score: float
    temporal_score: float
    importance_score: float
    access_score: float
    is_pinned: bool = False
    source: str = "user_input"
    metadata: dict = field(default_factory=dict)


# ============================================================================
# SYNC helpers (scheduler, background)
# ============================================================================

def _json_dumps(obj: Any) -> str:
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, default=str)


def _engine():
    """Reuse the sync engine from user_store."""
    from app.user_store import _engine as _get_engine
    return _get_engine()


# ============================================================================
# MemoryManager — the public interface
# ============================================================================

class MemoryManager:
    """
    Temporal memory system for Founder OS.

    All public methods come in sync and async variants.
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        embedding_provider=None,
    ):
        self.weights = weights or DEFAULT_WEIGHTS.copy()
        self._embedding_provider = embedding_provider  # lazy-init if None

    # ────────────────────────────────────────────────────────────
    # Embedding helper
    # ────────────────────────────────────────────────────────────

    async def _get_embedding(self, text: str) -> list[float] | None:
        """Generate an embedding vector for text using the configured provider."""
        if self._embedding_provider is None:
            try:
                # Settings-driven factory (honors EMBEDDING_PROVIDER/MODEL) with
                # a best-effort Redis cache — a raw OllamaEmbeddings() here
                # ignored the configured provider (task 020 / ADR-014 Q4 fix).
                from app.retrieval.embeddings import get_default_embedder
                try:
                    from app.redis import get_redis
                    redis = get_redis()
                except Exception:
                    redis = None  # uncached fallback, never fatal
                self._embedding_provider = get_default_embedder(redis=redis)
            except Exception as exc:
                logger.warning("Could not init embedding provider: %s", exc)
                return None
        try:
            return await self._embedding_provider.embed(text)
        except Exception as exc:
            logger.warning("Embedding generation failed: %s", exc)
            return None

    # ================================================================
    # STORE — add a memory page
    # ================================================================

    def store(
        self,
        user_id: str,
        title: str,
        content: str,
        *,
        page_type: str = "event",
        occurred_at: datetime | None = None,
        importance: float = 0.5,
        decay_rate: float = 0.001,
        chapter: str | None = None,
        tags: list[str] | None = None,
        entities: dict | None = None,
        summary: str | None = None,
        source: str = "user_input",
        is_pinned: bool = False,
        review_in_days: int | None = None,
        parent_id: uuid.UUID | None = None,
        embedding: list[float] | None = None,
        metadata: dict | None = None,
    ) -> uuid.UUID:
        """Synchronously store a new memory page. Returns the page ID."""
        from sqlalchemy import text as sa_text

        now = datetime.now(timezone.utc)
        page_id = uuid.uuid4()
        occurred = occurred_at or now

        next_review = None
        review_interval = None
        if review_in_days is not None:
            next_review = now + timedelta(days=review_in_days)
            review_interval = review_in_days

        try:
            with _engine().begin() as conn:
                conn.execute(
                    sa_text("""
                        INSERT INTO memory_pages (
                            id, user_id, page_type, title, content, summary,
                            occurred_at, importance, decay_rate, is_pinned,
                            next_review_at, review_interval_days,
                            chapter, tags, entities, parent_id,
                            embedding, source, metadata_
                        ) VALUES (
                            :id, :user_id, :page_type, :title, :content, :summary,
                            :occurred_at, :importance, :decay_rate, :is_pinned,
                            :next_review_at, :review_interval_days,
                            :chapter, :tags, :entities::jsonb, :parent_id,
                            :embedding, :source, :metadata::jsonb
                        )
                    """),
                    {
                        "id": page_id,
                        "user_id": user_id,
                        "page_type": page_type,
                        "title": title,
                        "content": content,
                        "summary": summary,
                        "occurred_at": occurred,
                        "importance": importance,
                        "decay_rate": decay_rate,
                        "is_pinned": is_pinned,
                        "next_review_at": next_review,
                        "review_interval_days": review_interval,
                        "chapter": chapter,
                        "tags": tags or [],
                        "entities": _json_dumps(entities or {}),
                        "parent_id": parent_id,
                        "embedding": str(embedding) if embedding else None,
                        "source": source,
                        "metadata": _json_dumps(metadata or {}),
                    },
                )
            logger.debug("Stored memory page %s for %s", page_id, user_id)
            return page_id
        except Exception as exc:
            logger.error("store() failed: %s", exc)
            raise

    async def async_store(
        self,
        user_id: str,
        title: str,
        content: str,
        *,
        page_type: str = "event",
        occurred_at: datetime | None = None,
        importance: float = 0.5,
        decay_rate: float = 0.001,
        chapter: str | None = None,
        tags: list[str] | None = None,
        entities: dict | None = None,
        summary: str | None = None,
        source: str = "user_input",
        is_pinned: bool = False,
        review_in_days: int | None = None,
        parent_id: uuid.UUID | None = None,
        embedding: list[float] | None = None,
        auto_embed: bool = True,
        metadata: dict | None = None,
    ) -> uuid.UUID:
        """Asynchronously store a new memory page."""
        from sqlalchemy import text as sa_text
        from app.database import async_session

        now = datetime.now(timezone.utc)
        page_id = uuid.uuid4()
        occurred = occurred_at or now

        next_review = None
        review_interval = None
        if review_in_days is not None:
            next_review = now + timedelta(days=review_in_days)
            review_interval = review_in_days

        # Auto-embed if no embedding provided
        if embedding is None and auto_embed:
            embedding = await self._get_embedding(f"{title}\n{content}")

        try:
            async with async_session() as session:
                await session.execute(
                    sa_text("""
                        INSERT INTO memory_pages (
                            id, user_id, page_type, title, content, summary,
                            occurred_at, importance, decay_rate, is_pinned,
                            next_review_at, review_interval_days,
                            chapter, tags, entities, parent_id,
                            embedding, source, metadata_
                        ) VALUES (
                            :id, :user_id, :page_type, :title, :content, :summary,
                            :occurred_at, :importance, :decay_rate, :is_pinned,
                            :next_review_at, :review_interval_days,
                            :chapter, :tags, CAST(:entities AS jsonb), :parent_id,
                            CAST(:embedding AS vector), :source, CAST(:metadata AS jsonb)
                        )
                    """),
                    {
                        "id": page_id,
                        "user_id": user_id,
                        "page_type": page_type,
                        "title": title,
                        "content": content,
                        "summary": summary,
                        "occurred_at": occurred,
                        "importance": importance,
                        "decay_rate": decay_rate,
                        "is_pinned": is_pinned,
                        "next_review_at": next_review,
                        "review_interval_days": review_interval,
                        "chapter": chapter,
                        "tags": tags or [],
                        "entities": _json_dumps(entities or {}),
                        "parent_id": parent_id,
                        "embedding": str(embedding) if embedding else None,
                        "source": source,
                        "metadata": _json_dumps(metadata or {}),
                    },
                )
                await session.commit()

            logger.debug("Async stored memory page %s for %s", page_id, sl(user_id))
            return page_id
        except Exception as exc:
            logger.error("async_store() failed: %s", exc)
            raise

    # ================================================================
    # RECALL — composite-scored retrieval
    # ================================================================

    def recall(
        self,
        user_id: str,
        query: str | None = None,
        *,
        limit: int = 10,
        chapter: str | None = None,
        page_type: str | None = None,
        tags: list[str] | None = None,
        min_importance: float = 0.0,
        since: datetime | None = None,
        until: datetime | None = None,
        include_pinned: bool = True,
        query_embedding: list[float] | None = None,
    ) -> list[MemoryHit]:
        """
        Synchronous composite-scored recall.

        If query_embedding is provided, includes semantic similarity in scoring.
        Otherwise retrieval is purely temporal + importance + access.
        """
        from sqlalchemy import text as sa_text

        now = datetime.now(timezone.utc)
        params: dict[str, Any] = {"user_id": user_id, "lim": limit * 3}
        filters = ["user_id = :user_id", "is_active = TRUE"]

        if chapter:
            filters.append("chapter = :chapter")
            params["chapter"] = chapter
        if page_type:
            filters.append("page_type = :ptype")
            params["ptype"] = page_type
        if min_importance > 0:
            filters.append("importance >= :min_imp")
            params["min_imp"] = min_importance
        if since:
            filters.append("occurred_at >= :since")
            params["since"] = since
        if until:
            filters.append("occurred_at <= :until")
            params["until"] = until
        if tags:
            filters.append("tags && :tags")
            params["tags"] = tags

        where = " AND ".join(filters)

        # Use the server-side temporal scoring function
        sql = f"""
            SELECT id, title, content, summary, page_type, chapter, tags,
                   entities, occurred_at, importance, decay_rate, is_pinned,
                   access_count, source, metadata_,
                   memory_temporal_score(importance, decay_rate, occurred_at, is_pinned)
                       AS temporal_score
            FROM memory_pages
            WHERE {where}
            ORDER BY temporal_score DESC
            LIMIT :lim
        """

        try:
            with _engine().connect() as conn:
                rows = conn.execute(sa_text(sql), params).fetchall()

                # Touch access counters
                if rows:
                    ids = [r.id for r in rows]
                    conn.execute(
                        sa_text("""
                            UPDATE memory_pages
                            SET access_count = access_count + 1,
                                last_accessed_at = NOW()
                            WHERE id = ANY(:ids)
                        """),
                        {"ids": ids},
                    )
                    conn.commit()

            return self._score_and_rank(rows, query_embedding, now, limit)

        except Exception as exc:
            logger.error("recall() failed: %s", exc)
            return []

    async def async_recall(
        self,
        user_id: str,
        query: str | None = None,
        *,
        limit: int = 10,
        chapter: str | None = None,
        page_type: str | None = None,
        tags: list[str] | None = None,
        min_importance: float = 0.0,
        since: datetime | None = None,
        until: datetime | None = None,
        include_pinned: bool = True,
        auto_embed_query: bool = True,
        query_embedding: list[float] | None = None,
    ) -> list[MemoryHit]:
        """Async composite-scored recall with auto-embedding of query.

        ``query_embedding`` mirrors the sync ``recall()``: when the caller
        already holds an embedding (e.g. BaseAgent.run()'s auto-embed step,
        ADR-014), pass it to skip the auto-embed and use the semantic branch.
        """
        from sqlalchemy import text as sa_text
        from app.database import async_session

        now = datetime.now(timezone.utc)
        if query_embedding is None and query and auto_embed_query:
            query_embedding = await self._get_embedding(query)

        params: dict[str, Any] = {"user_id": user_id, "lim": limit * 3}
        filters = ["user_id = :user_id", "is_active = TRUE"]

        if chapter:
            filters.append("chapter = :chapter")
            params["chapter"] = chapter
        if page_type:
            filters.append("page_type = :ptype")
            params["ptype"] = page_type
        if min_importance > 0:
            filters.append("importance >= :min_imp")
            params["min_imp"] = min_importance
        if since:
            filters.append("occurred_at >= :since")
            params["since"] = since
        if until:
            filters.append("occurred_at <= :until")
            params["until"] = until
        if tags:
            filters.append("tags && :tags")
            params["tags"] = tags

        where = " AND ".join(filters)

        # If we have an embedding, include cosine distance in SQL
        if query_embedding is not None:
            sql = f"""
                SELECT id, title, content, summary, page_type, chapter, tags,
                       entities, occurred_at, importance, decay_rate, is_pinned,
                       access_count, source, metadata_,
                       memory_temporal_score(importance, decay_rate, occurred_at, is_pinned)
                           AS temporal_score,
                       1 - (embedding <=> CAST(:qemb AS vector)) AS semantic_sim
                FROM memory_pages
                WHERE {where} AND embedding IS NOT NULL
                ORDER BY (
                    {self.weights['semantic']} * (1 - (embedding <=> CAST(:qemb AS vector)))
                    + {self.weights['temporal']} * memory_temporal_score(importance, decay_rate, occurred_at, is_pinned)
                    + {self.weights['importance']} * importance
                    + {self.weights['access']} * LEAST(access_count::float / 100.0, 1.0)
                ) DESC
                LIMIT :lim
            """
            params["qemb"] = str(query_embedding)
        else:
            sql = f"""
                SELECT id, title, content, summary, page_type, chapter, tags,
                       entities, occurred_at, importance, decay_rate, is_pinned,
                       access_count, source, metadata_,
                       memory_temporal_score(importance, decay_rate, occurred_at, is_pinned)
                           AS temporal_score,
                       0.0 AS semantic_sim
                FROM memory_pages
                WHERE {where}
                ORDER BY temporal_score DESC
                LIMIT :lim
            """

        try:
            async with async_session() as session:
                result = await session.execute(sa_text(sql), params)
                rows = result.fetchall()

                if rows:
                    ids = [r.id for r in rows]
                    await session.execute(
                        sa_text("""
                            UPDATE memory_pages
                            SET access_count = access_count + 1,
                                last_accessed_at = NOW()
                            WHERE id = ANY(:ids)
                        """),
                        {"ids": ids},
                    )
                    await session.commit()

            return self._score_and_rank(rows, query_embedding, now, limit)

        except Exception as exc:
            logger.error("async_recall() failed: %s", exc)
            return []

    def _score_and_rank(
        self,
        rows,
        query_embedding: list[float] | None,
        now: datetime,
        limit: int,
    ) -> list[MemoryHit]:
        """Apply the composite scoring formula in Python and return sorted results."""
        w = self.weights
        hits: list[MemoryHit] = []

        for r in rows:
            temporal = float(r.temporal_score) if r.temporal_score else 0.0
            sem = float(r.semantic_sim) if hasattr(r, "semantic_sim") and r.semantic_sim else 0.0
            imp = float(r.importance) if r.importance else 0.0
            acc = min(float(r.access_count or 0) / 100.0, 1.0)

            composite = (
                w["semantic"] * sem
                + w["temporal"] * temporal
                + w["importance"] * imp
                + w["access"] * acc
            )

            # If we had no embedding for the query, redistribute semantic weight
            if query_embedding is None:
                composite = (
                    (w["temporal"] + w["semantic"] * 0.5) * temporal
                    + (w["importance"] + w["semantic"] * 0.3) * imp
                    + (w["access"] + w["semantic"] * 0.2) * acc
                )

            hits.append(MemoryHit(
                id=r.id,
                title=r.title,
                content=r.content,
                summary=r.summary,
                page_type=r.page_type,
                chapter=r.chapter,
                tags=r.tags or [],
                entities=r.entities or {},
                occurred_at=r.occurred_at,
                importance=imp,
                composite_score=round(composite, 6),
                semantic_score=round(sem, 6),
                temporal_score=round(temporal, 6),
                importance_score=round(imp, 6),
                access_score=round(acc, 6),
                is_pinned=r.is_pinned,
                source=r.source or "user_input",
                metadata=r.metadata_ or {},
            ))

        hits.sort(key=lambda h: h.composite_score, reverse=True)
        return hits[:limit]

    # ================================================================
    # REVIEW — spaced-repetition lifecycle
    # ================================================================

    def get_due_reviews(self, user_id: str, limit: int = 20) -> list[MemoryHit]:
        """Sync: fetch memory pages that are due for review."""
        from sqlalchemy import text as sa_text

        now = datetime.now(timezone.utc)
        try:
            with _engine().connect() as conn:
                rows = conn.execute(
                    sa_text("""
                        SELECT id, title, content, summary, page_type, chapter,
                               tags, entities, occurred_at, importance, decay_rate,
                               is_pinned, access_count, source, metadata_,
                               memory_temporal_score(importance, decay_rate, occurred_at, is_pinned)
                                   AS temporal_score,
                               0.0 AS semantic_sim
                        FROM memory_pages
                        WHERE user_id = :uid AND is_active = TRUE
                          AND next_review_at IS NOT NULL
                          AND next_review_at <= :now
                        ORDER BY importance DESC, next_review_at ASC
                        LIMIT :lim
                    """),
                    {"uid": user_id, "now": now, "lim": limit},
                ).fetchall()

            return self._score_and_rank(rows, None, now, limit)
        except Exception as exc:
            logger.error("get_due_reviews() failed: %s", exc)
            return []

    async def async_get_due_reviews(self, user_id: str, limit: int = 20) -> list[MemoryHit]:
        """Async: fetch memory pages due for review."""
        from sqlalchemy import text as sa_text
        from app.database import async_session

        now = datetime.now(timezone.utc)
        try:
            async with async_session() as session:
                result = await session.execute(
                    sa_text("""
                        SELECT id, title, content, summary, page_type, chapter,
                               tags, entities, occurred_at, importance, decay_rate,
                               is_pinned, access_count, source, metadata_,
                               memory_temporal_score(importance, decay_rate, occurred_at, is_pinned)
                                   AS temporal_score,
                               0.0 AS semantic_sim
                        FROM memory_pages
                        WHERE user_id = :uid AND is_active = TRUE
                          AND next_review_at IS NOT NULL
                          AND next_review_at <= :now
                        ORDER BY importance DESC, next_review_at ASC
                        LIMIT :lim
                    """),
                    {"uid": user_id, "now": now, "lim": limit},
                )
                rows = result.fetchall()

            return self._score_and_rank(rows, None, now, limit)
        except Exception as exc:
            logger.error("async_get_due_reviews() failed: %s", exc)
            return []

    def mark_reviewed(self, page_id: uuid.UUID) -> None:
        """Mark a memory as reviewed and advance its review interval."""
        from sqlalchemy import text as sa_text

        now = datetime.now(timezone.utc)
        try:
            with _engine().begin() as conn:
                row = conn.execute(
                    sa_text("SELECT review_count, review_interval_days FROM memory_pages WHERE id = :pid"),
                    {"pid": page_id},
                ).fetchone()

                if not row:
                    return

                count = (row.review_count or 0) + 1
                idx = min(count, len(REVIEW_INTERVALS) - 1)
                next_interval = REVIEW_INTERVALS[idx]
                next_review = now + timedelta(days=next_interval)

                conn.execute(
                    sa_text("""
                        UPDATE memory_pages
                        SET review_count = :cnt,
                            review_interval_days = :interval,
                            next_review_at = :next_review,
                            last_reviewed_at = :now
                        WHERE id = :pid
                    """),
                    {
                        "cnt": count,
                        "interval": next_interval,
                        "next_review": next_review,
                        "now": now,
                        "pid": page_id,
                    },
                )
        except Exception as exc:
            logger.error("mark_reviewed() failed: %s", exc)

    async def async_mark_reviewed(self, page_id: uuid.UUID) -> None:
        """Async: mark a memory as reviewed and advance its review interval."""
        from sqlalchemy import text as sa_text
        from app.database import async_session

        now = datetime.now(timezone.utc)
        try:
            async with async_session() as session:
                result = await session.execute(
                    sa_text("SELECT review_count, review_interval_days FROM memory_pages WHERE id = :pid"),
                    {"pid": page_id},
                )
                row = result.fetchone()
                if not row:
                    return

                count = (row.review_count or 0) + 1
                idx = min(count, len(REVIEW_INTERVALS) - 1)
                next_interval = REVIEW_INTERVALS[idx]
                next_review = now + timedelta(days=next_interval)

                await session.execute(
                    sa_text("""
                        UPDATE memory_pages
                        SET review_count = :cnt,
                            review_interval_days = :interval,
                            next_review_at = :next_review,
                            last_reviewed_at = :now
                        WHERE id = :pid
                    """),
                    {
                        "cnt": count,
                        "interval": next_interval,
                        "next_review": next_review,
                        "now": now,
                        "pid": page_id,
                    },
                )
                await session.commit()
        except Exception as exc:
            logger.error("async_mark_reviewed() failed: %s", exc)

    # ================================================================
    # BROWSE BY CHAPTER
    # ================================================================

    async def async_browse_chapter(
        self,
        user_id: str,
        chapter: str,
        *,
        limit: int = 50,
        offset: int = 0,
        order: str = "desc",
    ) -> list[MemoryHit]:
        """Browse memories within a chapter, ordered chronologically."""
        from sqlalchemy import text as sa_text
        from app.database import async_session

        now = datetime.now(timezone.utc)
        direction = "DESC" if order == "desc" else "ASC"
        try:
            async with async_session() as session:
                result = await session.execute(
                    sa_text(f"""
                        SELECT id, title, content, summary, page_type, chapter,
                               tags, entities, occurred_at, importance, decay_rate,
                               is_pinned, access_count, source, metadata_,
                               memory_temporal_score(importance, decay_rate, occurred_at, is_pinned)
                                   AS temporal_score,
                               0.0 AS semantic_sim
                        FROM memory_pages
                        WHERE user_id = :uid AND chapter = :ch AND is_active = TRUE
                        ORDER BY occurred_at {direction}
                        LIMIT :lim OFFSET :off
                    """),
                    {"uid": user_id, "ch": chapter, "lim": limit, "off": offset},
                )
                rows = result.fetchall()

            return self._score_and_rank(rows, None, now, limit)
        except Exception as exc:
            logger.error("async_browse_chapter() failed: %s", exc)
            return []

    # ================================================================
    # ENTITY SEARCH
    # ================================================================

    async def async_search_entities(
        self,
        user_id: str,
        entity_query: str,
        *,
        limit: int = 20,
    ) -> list[MemoryHit]:
        """Find memories mentioning a specific entity (person, company, tool)."""
        from sqlalchemy import text as sa_text
        from app.database import async_session

        now = datetime.now(timezone.utc)
        try:
            async with async_session() as session:
                result = await session.execute(
                    sa_text("""
                        SELECT id, title, content, summary, page_type, chapter,
                               tags, entities, occurred_at, importance, decay_rate,
                               is_pinned, access_count, source, metadata_,
                               memory_temporal_score(importance, decay_rate, occurred_at, is_pinned)
                                   AS temporal_score,
                               0.0 AS semantic_sim
                        FROM memory_pages
                        WHERE user_id = :uid AND is_active = TRUE
                          AND (
                            entities::text ILIKE :eq
                            OR content ILIKE :eq
                            OR title ILIKE :eq
                          )
                        ORDER BY temporal_score DESC
                        LIMIT :lim
                    """),
                    {"uid": user_id, "eq": f"%{entity_query}%", "lim": limit},
                )
                rows = result.fetchall()

            return self._score_and_rank(rows, None, now, limit)
        except Exception as exc:
            logger.error("async_search_entities() failed: %s", exc)
            return []

    # ================================================================
    # LINK — create typed relationships between memories
    # ================================================================

    async def async_link(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        link_type: str = "related",
        strength: float = 0.5,
        metadata: dict | None = None,
    ) -> uuid.UUID:
        """Create a typed link between two memory pages."""
        from sqlalchemy import text as sa_text
        from app.database import async_session

        link_id = uuid.uuid4()
        try:
            async with async_session() as session:
                await session.execute(
                    sa_text("""
                        INSERT INTO memory_links (id, source_id, target_id, link_type, strength, metadata_)
                        VALUES (:id, :src, :tgt, :lt, :str, CAST(:meta AS jsonb))
                        ON CONFLICT (source_id, target_id, link_type) DO UPDATE SET
                            strength = EXCLUDED.strength,
                            metadata_ = EXCLUDED.metadata_
                    """),
                    {
                        "id": link_id,
                        "src": source_id,
                        "tgt": target_id,
                        "lt": link_type,
                        "str": strength,
                        "meta": _json_dumps(metadata or {}),
                    },
                )
                await session.commit()
            return link_id
        except Exception as exc:
            logger.error("async_link() failed: %s", exc)
            raise

    async def async_get_linked(
        self,
        page_id: uuid.UUID,
        *,
        link_type: str | None = None,
        direction: str = "both",
    ) -> list[dict]:
        """Get memories linked to a given page."""
        from sqlalchemy import text as sa_text
        from app.database import async_session

        conditions = []
        if direction in ("both", "outgoing"):
            cond = "ml.source_id = :pid"
            if link_type:
                cond += " AND ml.link_type = :lt"
            conditions.append(f"({cond})")
        if direction in ("both", "incoming"):
            cond = "ml.target_id = :pid"
            if link_type:
                cond += " AND ml.link_type = :lt"
            conditions.append(f"({cond})")

        where = " OR ".join(conditions)
        params: dict[str, Any] = {"pid": page_id}
        if link_type:
            params["lt"] = link_type

        try:
            async with async_session() as session:
                result = await session.execute(
                    sa_text(f"""
                        SELECT ml.id AS link_id, ml.link_type, ml.strength,
                               ml.source_id, ml.target_id,
                               mp.title, mp.page_type, mp.occurred_at, mp.importance
                        FROM memory_links ml
                        JOIN memory_pages mp ON (
                            CASE WHEN ml.source_id = :pid THEN ml.target_id
                                 ELSE ml.source_id END = mp.id
                        )
                        WHERE {where}
                        ORDER BY ml.strength DESC
                    """),
                    params,
                )
                rows = result.fetchall()
                return [
                    {
                        "link_id": str(r.link_id),
                        "link_type": r.link_type,
                        "strength": float(r.strength),
                        "page_id": str(r.target_id if r.source_id == page_id else r.source_id),
                        "title": r.title,
                        "page_type": r.page_type,
                        "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
                        "importance": float(r.importance) if r.importance else 0,
                    }
                    for r in rows
                ]
        except Exception as exc:
            logger.error("async_get_linked() failed: %s", exc)
            return []

    # ================================================================
    # STATS — summary for a user
    # ================================================================

    async def async_stats(self, user_id: str) -> dict:
        """Memory system stats for a user."""
        from sqlalchemy import text as sa_text
        from app.database import async_session

        try:
            async with async_session() as session:
                result = await session.execute(
                    sa_text("""
                        SELECT
                            COUNT(*) FILTER (WHERE is_active) AS total,
                            COUNT(*) FILTER (WHERE is_pinned) AS pinned,
                            COUNT(DISTINCT chapter) FILTER (WHERE chapter IS NOT NULL) AS chapters,
                            COUNT(*) FILTER (WHERE next_review_at IS NOT NULL AND next_review_at <= NOW()) AS reviews_due,
                            AVG(importance) AS avg_importance,
                            MIN(occurred_at) AS earliest,
                            MAX(occurred_at) AS latest
                        FROM memory_pages
                        WHERE user_id = :uid
                    """),
                    {"uid": user_id},
                )
                row = result.fetchone()
                if not row:
                    return {"total": 0}

                return {
                    "total_memories": row.total or 0,
                    "pinned": row.pinned or 0,
                    "chapters": row.chapters or 0,
                    "reviews_due": row.reviews_due or 0,
                    "avg_importance": round(float(row.avg_importance or 0), 3),
                    "earliest_memory": row.earliest.isoformat() if row.earliest else None,
                    "latest_memory": row.latest.isoformat() if row.latest else None,
                }
        except Exception as exc:
            logger.error("async_stats() failed: %s", exc)
            return {"total": 0, "error": str(exc)}

    # ================================================================
    # DELETE (soft)
    # ================================================================

    async def async_delete(self, page_id: uuid.UUID) -> bool:
        """Soft-delete a memory page."""
        from sqlalchemy import text as sa_text
        from app.database import async_session

        try:
            async with async_session() as session:
                result = await session.execute(
                    sa_text("UPDATE memory_pages SET is_active = FALSE WHERE id = :pid"),
                    {"pid": page_id},
                )
                await session.commit()
                return result.rowcount > 0
        except Exception as exc:
            logger.error("async_delete() failed: %s", exc)
            return False

    # ================================================================
    # PIN / UNPIN
    # ================================================================

    async def async_pin(self, page_id: uuid.UUID, pin: bool = True) -> bool:
        """Pin or unpin a memory (pinned = never decays)."""
        from sqlalchemy import text as sa_text
        from app.database import async_session

        try:
            async with async_session() as session:
                result = await session.execute(
                    sa_text("UPDATE memory_pages SET is_pinned = :pin WHERE id = :pid"),
                    {"pin": pin, "pid": page_id},
                )
                await session.commit()
                return result.rowcount > 0
        except Exception as exc:
            logger.error("async_pin() failed: %s", exc)
            return False

    # ================================================================
    # CONTEXT INJECTION — format memories for LLM context window
    # ================================================================

    def format_for_llm(
        self,
        memories: list[MemoryHit],
        *,
        max_chars: int = 6000,
        include_metadata: bool = True,
    ) -> str:
        """
        Format recalled memories as structured context for LLM injection.

        Returns an XML-like structure that LLMs handle well for context.
        """
        if not memories:
            return "<memories>No relevant memories found.</memories>"

        parts = ["<memories>"]
        chars = 0
        for i, m in enumerate(memories, 1):
            entry = f"""<memory rank="{i}" type="{m.page_type}" score="{m.composite_score:.3f}">
  <title>{m.title}</title>
  <when>{m.occurred_at.strftime('%Y-%m-%d')}</when>"""
            if m.chapter:
                entry += f"\n  <chapter>{m.chapter}</chapter>"
            if include_metadata and m.tags:
                entry += f"\n  <tags>{', '.join(m.tags)}</tags>"
            entry += f"\n  <content>{m.summary or m.content}</content>"
            entry += "\n</memory>"

            if chars + len(entry) > max_chars:
                break
            parts.append(entry)
            chars += len(entry)

        parts.append("</memories>")
        return "\n".join(parts)

    # ================================================================
    # CHAPTERS LIST
    # ================================================================

    async def async_list_chapters(self, user_id: str) -> list[dict]:
        """List all chapters with page counts for a user."""
        from sqlalchemy import text as sa_text
        from app.database import async_session

        try:
            async with async_session() as session:
                result = await session.execute(
                    sa_text("""
                        SELECT chapter,
                               COUNT(*) AS count,
                               MAX(occurred_at) AS latest,
                               AVG(importance) AS avg_importance
                        FROM memory_pages
                        WHERE user_id = :uid AND is_active = TRUE AND chapter IS NOT NULL
                        GROUP BY chapter
                        ORDER BY latest DESC
                    """),
                    {"uid": user_id},
                )
                rows = result.fetchall()
                return [
                    {
                        "chapter": r.chapter,
                        "count": r.count,
                        "latest": r.latest.isoformat() if r.latest else None,
                        "avg_importance": round(float(r.avg_importance or 0), 3),
                    }
                    for r in rows
                ]
        except Exception as exc:
            logger.error("async_list_chapters() failed: %s", exc)
            return []


# ============================================================================
# Module-level singleton
# ============================================================================

_manager: MemoryManager | None = None


def get_memory_manager() -> MemoryManager:
    """Get or create the singleton MemoryManager."""
    global _manager
    if _manager is None:
        _manager = MemoryManager()
    return _manager
