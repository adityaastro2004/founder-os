"""
Founder OS — Context Retriever
=================================
High-level retrieval service that agents use for RAG context augmentation.

Combines:
  - Hybrid search (semantic + full-text via VectorStore)
  - Smart re-ranking (boost recent, boost previously-useful items)
  - Context formatting (XML-tagged blocks for LLM consumption)
  - Usage tracking (records which knowledge items were retrieved)
  - Auto-embedding of query text

This is the main interface agents should use via ``BaseAgent.run()``.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.retrieval.embeddings import EmbeddingProvider
from app.retrieval.vector_store import VectorStore, SearchResult

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """A single retrieval result with enriched metadata."""
    id: uuid.UUID
    title: str | None
    content: str
    category: str | None
    tags: list[str] | None
    score: float
    source_url: str | None = None
    metadata: dict = field(default_factory=dict)


class ContextRetriever:
    """
    High-level context retrieval service for agents.

    Usage:
        retriever = ContextRetriever(db=session, embedder=embedder, user_id=uid)

        # Search with auto-embedding
        results = await retriever.search("pricing strategy for enterprise")

        # Get formatted context for LLM injection
        context = await retriever.get_context("pricing strategy for enterprise")
    """

    def __init__(
        self,
        db: AsyncSession,
        embedder: EmbeddingProvider,
        user_id: uuid.UUID,
    ) -> None:
        self._db = db
        self._embedder = embedder
        self._user_id = user_id
        self._store = VectorStore(db)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        min_similarity: float = 0.5,
        category: str | None = None,
        tags: list[str] | None = None,
        search_type: str = "hybrid",   # "hybrid" | "semantic" | "fulltext" | "mmr"
    ) -> list[RetrievalResult]:
        """
        Search knowledge items with auto-embedding.

        Args:
            query: Natural language search query.
            limit: Max results to return.
            min_similarity: Minimum cosine similarity threshold.
            category: Filter by category.
            tags: Filter by tags (any match).
            search_type: "hybrid" (default), "semantic", "fulltext", or "mmr".

        Returns:
            Ranked list of RetrievalResult objects.
        """
        results: list[SearchResult] = []

        if search_type in ("hybrid", "semantic", "mmr"):
            # Embed the query
            query_embedding = await self._embedder.embed(query)

            if search_type == "mmr":
                results = await self._store.search_mmr(
                    user_id=self._user_id,
                    query_embedding=query_embedding,
                    limit=limit,
                    min_similarity=min_similarity,
                    category=category,
                    tags=tags,
                )
            elif search_type == "hybrid":
                results = await self._store.hybrid_search(
                    user_id=self._user_id,
                    query=query,
                    query_embedding=query_embedding,
                    limit=limit,
                    min_similarity=min_similarity,
                    category=category,
                )
            else:
                results = await self._store.search(
                    user_id=self._user_id,
                    query_embedding=query_embedding,
                    limit=limit,
                    min_similarity=min_similarity,
                    category=category,
                    tags=tags,
                )
        elif search_type == "fulltext":
            results = await self._store.fulltext_search(
                user_id=self._user_id,
                query=query,
                limit=limit,
                category=category,
            )
        else:
            raise ValueError(f"Unknown search_type: {search_type}")

        # Track usage (update reference counts)
        for r in results:
            await self._store.update_reference_count(r.id)

        return [
            RetrievalResult(
                id=r.id,
                title=r.title,
                content=r.content,
                category=r.category,
                tags=r.tags,
                score=r.score,
                source_url=r.source_url,
                metadata=r.metadata,
            )
            for r in results
        ]

    # ------------------------------------------------------------------
    # Context formatting for LLM injection
    # ------------------------------------------------------------------

    async def get_context(
        self,
        query: str,
        *,
        limit: int = 5,
        min_similarity: float = 0.5,
        category: str | None = None,
        search_type: str = "hybrid",
    ) -> str:
        """
        Search and format results as an XML-tagged context block
        suitable for injection into an LLM system prompt.

        Returns empty string if no relevant context is found.
        """
        results = await self.search(
            query,
            limit=limit,
            min_similarity=min_similarity,
            category=category,
            search_type=search_type,
        )

        if not results:
            return ""

        parts = ["<knowledge_context>"]
        for i, r in enumerate(results, 1):
            title = r.title or "Untitled"
            cat = f" [{r.category}]" if r.category else ""
            score_str = f"{r.score:.3f}"
            parts.append(
                f"<item rank=\"{i}\" relevance=\"{score_str}\">\n"
                f"<title>{title}{cat}</title>\n"
                f"<content>{r.content}</content>\n"
                f"</item>"
            )
        parts.append("</knowledge_context>")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Embed a query (utility for external callers)
    # ------------------------------------------------------------------

    async def embed_query(self, query: str) -> list[float]:
        """Generate embedding for a query string."""
        return await self._embedder.embed(query)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    async def get_stats(self) -> dict[str, Any]:
        """Get knowledge base statistics for this user."""
        total = await self._store.count(self._user_id)
        with_embeddings = await self._store.count(self._user_id, has_embedding=True)

        return {
            "total_items": total,
            "items_with_embeddings": with_embeddings,
            "items_without_embeddings": total - with_embeddings,
            "embedding_model": self._embedder.model,
            "embedding_dimensions": self._embedder.dimensions,
        }
