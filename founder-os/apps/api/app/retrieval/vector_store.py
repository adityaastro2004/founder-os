"""
Founder OS — Vector Store
============================
pgvector-backed vector storage and retrieval for knowledge items.

Operations:
  - upsert (insert/update with embedding)
  - search (cosine similarity)
  - hybrid_search (cosine + full-text ts_rank, RRF fusion)
  - delete, count, exists
  - bulk_upsert (batch operations)

All operations go through the existing ``knowledge_items`` table
which has:
  - ``embedding vector(1536)`` column
  - ``ivfflat`` index on embeddings
  - ``GIN`` index on ``to_tsvector('english', content)``
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import text, select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeItem

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result from the vector store."""
    id: uuid.UUID
    title: str | None
    content: str
    category: str | None
    tags: list[str] | None
    score: float             # cosine similarity (0–1) or hybrid score
    source_url: str | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def similarity(self) -> float:
        return self.score


class VectorStore:
    """
    Vector store backed by PostgreSQL + pgvector.

    Wraps the ``knowledge_items`` table with vector operations.
    Supports:
      - Semantic search (cosine similarity via pgvector)
      - Full-text search (PostgreSQL tsvector/tsquery)
      - Hybrid search (Reciprocal Rank Fusion of both)
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------

    async def upsert(
        self,
        user_id: uuid.UUID,
        content: str,
        embedding: list[float],
        *,
        title: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        source_url: str | None = None,
        content_type: str = "text",
        file_path: str | None = None,
        file_size_bytes: int | None = None,
        mime_type: str | None = None,
        item_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """
        Insert or update a knowledge item with its embedding.

        If item_id is provided and exists, updates it. Otherwise creates new.
        """
        if item_id:
            # Check if exists
            existing = await self._db.get(KnowledgeItem, item_id)
            if existing:
                existing.content = content
                existing.embedding = embedding
                existing.title = title or existing.title
                existing.category = category or existing.category
                existing.tags = tags or existing.tags
                existing.source_url = source_url or existing.source_url
                existing.processing_status = "completed"
                await self._db.flush()
                return item_id

        # Create new
        item = KnowledgeItem(
            id=item_id or uuid.uuid4(),
            user_id=user_id,
            title=title,
            content=content,
            content_type=content_type,
            source_url=source_url,
            category=category,
            tags=tags,
            embedding=embedding,
            file_path=file_path,
            file_size_bytes=file_size_bytes,
            mime_type=mime_type,
            processing_status="completed",
        )
        self._db.add(item)
        await self._db.flush()
        return item.id

    async def bulk_upsert(
        self,
        user_id: uuid.UUID,
        items: list[dict[str, Any]],
    ) -> list[uuid.UUID]:
        """
        Batch upsert multiple knowledge items.

        Each dict in items should have:
          - content (str)
          - embedding (list[float])
          - title (optional str)
          - category (optional str)
          - tags (optional list[str])
          - source_url (optional str)
        """
        ids: list[uuid.UUID] = []
        for item_data in items:
            item_id = await self.upsert(
                user_id=user_id,
                content=item_data["content"],
                embedding=item_data["embedding"],
                title=item_data.get("title"),
                category=item_data.get("category"),
                tags=item_data.get("tags"),
                source_url=item_data.get("source_url"),
                content_type=item_data.get("content_type", "text"),
            )
            ids.append(item_id)
        return ids

    # ------------------------------------------------------------------
    # Semantic Search (cosine similarity)
    # ------------------------------------------------------------------

    async def search(
        self,
        user_id: uuid.UUID,
        query_embedding: list[float],
        *,
        limit: int = 10,
        min_similarity: float = 0.5,
        category: str | None = None,
        tags: list[str] | None = None,
    ) -> list[SearchResult]:
        """
        Semantic search using cosine similarity.

        Uses pgvector's ``<=>`` (cosine distance) operator + ivfflat index.
        """
        filters = ["ki.user_id = :uid", "ki.is_active = true", "ki.embedding IS NOT NULL"]
        params: dict[str, Any] = {
            "uid": user_id,
            "emb": str(query_embedding),
            "lim": limit,
        }

        if category:
            filters.append("ki.category = :cat")
            params["cat"] = category

        if tags:
            filters.append("ki.tags && :tags")
            params["tags"] = tags

        where_clause = " AND ".join(filters)

        sql = text(f"""
            SELECT
                ki.id,
                ki.title,
                ki.content,
                ki.category,
                ki.tags,
                ki.source_url,
                                1 - (ki.embedding <=> CAST(:emb AS vector)) AS similarity
            FROM knowledge_items ki
            WHERE {where_clause}
                            AND 1 - (ki.embedding <=> CAST(:emb AS vector)) >= :min_sim
                        ORDER BY ki.embedding <=> CAST(:emb AS vector)
            LIMIT :lim
        """)
        params["min_sim"] = min_similarity

        result = await self._db.execute(sql, params)
        rows = result.fetchall()

        return [
            SearchResult(
                id=row.id,
                title=row.title,
                content=row.content,
                category=row.category,
                tags=row.tags,
                source_url=row.source_url,
                score=float(row.similarity),
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Full-text Search
    # ------------------------------------------------------------------

    async def fulltext_search(
        self,
        user_id: uuid.UUID,
        query: str,
        *,
        limit: int = 10,
        category: str | None = None,
    ) -> list[SearchResult]:
        """
        Full-text search using PostgreSQL tsvector/tsquery.

        Uses the GIN index on ``to_tsvector('english', content)``.
        """
        filters = ["ki.user_id = :uid", "ki.is_active = true"]
        params: dict[str, Any] = {
            "uid": user_id,
            "query": query,
            "lim": limit,
        }

        if category:
            filters.append("ki.category = :cat")
            params["cat"] = category

        where_clause = " AND ".join(filters)

        sql = text(f"""
            SELECT
                ki.id,
                ki.title,
                ki.content,
                ki.category,
                ki.tags,
                ki.source_url,
                ts_rank_cd(
                    to_tsvector('english', ki.content),
                    plainto_tsquery('english', :query)
                ) AS rank
            FROM knowledge_items ki
            WHERE {where_clause}
              AND to_tsvector('english', ki.content) @@ plainto_tsquery('english', :query)
            ORDER BY rank DESC
            LIMIT :lim
        """)

        result = await self._db.execute(sql, params)
        rows = result.fetchall()

        return [
            SearchResult(
                id=row.id,
                title=row.title,
                content=row.content,
                category=row.category,
                tags=row.tags,
                source_url=row.source_url,
                score=float(row.rank),
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Hybrid Search (RRF — Reciprocal Rank Fusion)
    # ------------------------------------------------------------------

    async def hybrid_search(
        self,
        user_id: uuid.UUID,
        query: str,
        query_embedding: list[float],
        *,
        limit: int = 10,
        min_similarity: float = 0.4,
        category: str | None = None,
        semantic_weight: float = 0.7,
        fulltext_weight: float = 0.3,
        rrf_k: int = 60,
    ) -> list[SearchResult]:
        """
        Hybrid search combining semantic similarity + full-text relevance
        using Reciprocal Rank Fusion (RRF).

        RRF formula: score = Σ (weight / (k + rank_i))
        This avoids score-scale mismatches between different ranking methods.

        Args:
            query: Natural language query for full-text search
            query_embedding: Pre-computed embedding for semantic search
            semantic_weight: Weight for cosine similarity ranking (0–1)
            fulltext_weight: Weight for full-text ranking (0–1)
            rrf_k: RRF smoothing constant (default 60)
        """
        filters = [
            "ki.user_id = :uid",
            "ki.is_active = true",
        ]
        params: dict[str, Any] = {
            "uid": user_id,
            "emb": str(query_embedding),
            "query": query,
            "lim": limit,
            "min_sim": min_similarity,
            "sem_w": semantic_weight,
            "ft_w": fulltext_weight,
            "rrf_k": rrf_k,
        }

        cat_filter = ""
        if category:
            cat_filter = "AND ki.category = :cat"
            params["cat"] = category

        sql = text(f"""
            WITH semantic AS (
                SELECT
                    ki.id,
                    ki.title,
                    ki.content,
                    ki.category,
                    ki.tags,
                    ki.source_url,
                    1 - (ki.embedding <=> CAST(:emb AS vector)) AS similarity,
                    ROW_NUMBER() OVER (ORDER BY ki.embedding <=> CAST(:emb AS vector)) AS sem_rank
                FROM knowledge_items ki
                WHERE ki.user_id = :uid
                  AND ki.is_active = true
                  AND ki.embedding IS NOT NULL
                  {cat_filter}
                ORDER BY ki.embedding <=> CAST(:emb AS vector)
                LIMIT :lim * 3
            ),
            fulltext AS (
                SELECT
                    ki.id,
                    ts_rank_cd(
                        to_tsvector('english', ki.content),
                        plainto_tsquery('english', :query)
                    ) AS ft_rank_score,
                    ROW_NUMBER() OVER (
                        ORDER BY ts_rank_cd(
                            to_tsvector('english', ki.content),
                            plainto_tsquery('english', :query)
                        ) DESC
                    ) AS ft_rank
                FROM knowledge_items ki
                WHERE ki.user_id = :uid
                  AND ki.is_active = true
                  AND to_tsvector('english', ki.content) @@ plainto_tsquery('english', :query)
                  {cat_filter}
                LIMIT :lim * 3
            )
            SELECT
                s.id,
                s.title,
                s.content,
                s.category,
                s.tags,
                s.source_url,
                s.similarity,
                COALESCE(:sem_w / (:rrf_k + s.sem_rank), 0)
                    + COALESCE(:ft_w / (:rrf_k + f.ft_rank), 0) AS hybrid_score
            FROM semantic s
            LEFT JOIN fulltext f ON s.id = f.id
            WHERE s.similarity >= :min_sim
            ORDER BY hybrid_score DESC
            LIMIT :lim
        """)

        result = await self._db.execute(sql, params)
        rows = result.fetchall()

        return [
            SearchResult(
                id=row.id,
                title=row.title,
                content=row.content,
                category=row.category,
                tags=row.tags,
                source_url=row.source_url,
                score=float(row.hybrid_score),
                metadata={"cosine_similarity": float(row.similarity)},
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Delete / Count / Exists
    # ------------------------------------------------------------------

    async def delete(self, item_id: uuid.UUID) -> bool:
        """Delete a knowledge item by ID."""
        result = await self._db.execute(
            delete(KnowledgeItem).where(KnowledgeItem.id == item_id)
        )
        await self._db.flush()
        return result.rowcount > 0

    async def delete_by_user(
        self,
        user_id: uuid.UUID,
        *,
        category: str | None = None,
    ) -> int:
        """Delete all knowledge items for a user (optionally filtered by category)."""
        stmt = delete(KnowledgeItem).where(KnowledgeItem.user_id == user_id)
        if category:
            stmt = stmt.where(KnowledgeItem.category == category)
        result = await self._db.execute(stmt)
        await self._db.flush()
        return result.rowcount

    async def count(
        self,
        user_id: uuid.UUID,
        *,
        category: str | None = None,
        has_embedding: bool = False,
    ) -> int:
        """Count knowledge items for a user."""
        stmt = select(func.count(KnowledgeItem.id)).where(
            KnowledgeItem.user_id == user_id,
            KnowledgeItem.is_active == True,
        )
        if category:
            stmt = stmt.where(KnowledgeItem.category == category)
        if has_embedding:
            stmt = stmt.where(KnowledgeItem.embedding.isnot(None))
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def exists(self, item_id: uuid.UUID) -> bool:
        """Check if a knowledge item exists."""
        result = await self._db.execute(
            select(func.count(KnowledgeItem.id)).where(KnowledgeItem.id == item_id)
        )
        return result.scalar_one() > 0

    async def update_reference_count(self, item_id: uuid.UUID) -> None:
        """Increment the reference counter when a knowledge item is used."""
        await self._db.execute(
            update(KnowledgeItem)
            .where(KnowledgeItem.id == item_id)
            .values(
                times_referenced=KnowledgeItem.times_referenced + 1,
                last_referenced_at=func.now(),
            )
        )
        await self._db.flush()

    # ------------------------------------------------------------------
    # MMR Search (Maximal Marginal Relevance)
    # ------------------------------------------------------------------

    async def search_mmr(
        self,
        user_id: uuid.UUID,
        query_embedding: list[float],
        *,
        limit: int = 5,
        candidates: int = 20,
        lambda_mult: float = 0.7,
        min_similarity: float = 0.4,
        category: str | None = None,
        tags: list[str] | None = None,
    ) -> list[SearchResult]:
        """
        Maximal Marginal Relevance search for diverse, relevant results.

        Fetches `candidates` nearest neighbours, then greedily selects
        `limit` items that balance relevance to the query against
        redundancy with already-selected items.

        MMR(d) = λ · sim(d, q) − (1−λ) · max_{s∈S} sim(d, s)

        Args:
            query_embedding: Query vector.
            limit: Final number of results.
            candidates: Size of initial candidate pool (should be > limit).
            lambda_mult: 0→max diversity, 1→max relevance. Default 0.7.
            min_similarity: Minimum cosine similarity for candidates.
            category: Optional category filter.
            tags: Optional tag filter.
        """
        # 1. Fetch candidate pool via cosine similarity
        filters = ["ki.user_id = :uid", "ki.is_active = true", "ki.embedding IS NOT NULL"]
        params: dict[str, Any] = {
            "uid": user_id,
            "emb": str(query_embedding),
            "lim": candidates,
            "min_sim": min_similarity,
        }
        if category:
            filters.append("ki.category = :cat")
            params["cat"] = category
        if tags:
            filters.append("ki.tags && :tags")
            params["tags"] = tags

        where_clause = " AND ".join(filters)

        sql = text(f"""
            SELECT
                ki.id,
                ki.title,
                ki.content,
                ki.category,
                ki.tags,
                ki.source_url,
                                1 - (ki.embedding <=> CAST(:emb AS vector)) AS similarity,
                ki.embedding::text AS emb_text
            FROM knowledge_items ki
            WHERE {where_clause}
                            AND 1 - (ki.embedding <=> CAST(:emb AS vector)) >= :min_sim
                        ORDER BY ki.embedding <=> CAST(:emb AS vector)
            LIMIT :lim
        """)

        result = await self._db.execute(sql, params)
        rows = result.fetchall()

        if not rows:
            return []

        # 2. Parse embeddings and build candidate list
        import json as _json

        _Candidate = type("_Candidate", (), {})
        pool: list[dict[str, Any]] = []
        for row in rows:
            emb_str = row.emb_text
            # pgvector returns "[0.1,0.2,...]" format
            try:
                emb = _json.loads(emb_str)
            except (ValueError, TypeError):
                emb = [float(x) for x in emb_str.strip("[]").split(",") if x.strip()]
            pool.append({
                "id": row.id,
                "title": row.title,
                "content": row.content,
                "category": row.category,
                "tags": row.tags,
                "source_url": row.source_url,
                "similarity": float(row.similarity),
                "embedding": emb,
            })

        # 3. Greedy MMR selection
        selected: list[dict[str, Any]] = []
        selected_embs: list[list[float]] = []
        remaining = list(range(len(pool)))

        for _ in range(min(limit, len(pool))):
            best_idx = -1
            best_score = float("-inf")

            for idx in remaining:
                cand = pool[idx]
                relevance = cand["similarity"]

                # Max similarity to already-selected items
                max_sim_to_selected = 0.0
                if selected_embs:
                    cand_emb = cand["embedding"]
                    for sel_emb in selected_embs:
                        sim = _cosine_sim(cand_emb, sel_emb)
                        if sim > max_sim_to_selected:
                            max_sim_to_selected = sim

                mmr_score = lambda_mult * relevance - (1 - lambda_mult) * max_sim_to_selected

                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = idx

            if best_idx < 0:
                break

            selected.append(pool[best_idx])
            selected_embs.append(pool[best_idx]["embedding"])
            remaining.remove(best_idx)

        return [
            SearchResult(
                id=s["id"],
                title=s["title"],
                content=s["content"],
                category=s["category"],
                tags=s["tags"],
                source_url=s["source_url"],
                score=s["similarity"],
            )
            for s in selected
        ]


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
