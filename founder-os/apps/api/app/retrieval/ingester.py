"""
Founder OS — Document Ingester
=================================
Pipeline for ingesting documents into the vector store.

Supports:
  - **Plain text** — direct content ingestion
  - **URL** — fetches content from a web page (HTML → text extraction)
  - **Structured data** — JSON, YAML, markdown
  - **Batch** — ingest multiple documents at once

Pipeline:
  1. Accept content (text, URL, file)
  2. Extract text (if URL/file)
  3. Chunk into token-aware segments
  4. Batch-embed all chunks
  5. Store in vector DB with metadata
  6. Return ingestion receipt
"""

from __future__ import annotations

import logging
import re
import uuid
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from app.retrieval.chunker import TextChunker, Chunk, count_tokens
from app.retrieval.embeddings import EmbeddingProvider
from app.retrieval.vector_store import VectorStore
from app.log_sanitize import sl

logger = logging.getLogger(__name__)

# Max batch size for embedding calls (avoid overwhelming providers)
EMBED_BATCH_SIZE = 64


@dataclass
class IngestionResult:
    """Result of a document ingestion."""
    document_id: str              # group ID for all chunks from this doc
    chunks_created: int
    total_tokens: int
    knowledge_item_ids: list[str]  # UUID strings of created knowledge items
    duration_seconds: float
    title: str | None = None
    category: str | None = None
    source_url: str | None = None


class Ingester:
    """
    Document ingestion pipeline.

    Orchestrates: content → chunk → embed → store.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        embedder: EmbeddingProvider,
        chunker: TextChunker | None = None,
    ) -> None:
        self._store = vector_store
        self._embedder = embedder
        self._chunker = chunker or TextChunker()

    # ------------------------------------------------------------------
    # Ingest plain text
    # ------------------------------------------------------------------

    async def ingest_text(
        self,
        user_id: uuid.UUID,
        content: str,
        *,
        title: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        source_url: str | None = None,
        metadata: dict | None = None,
    ) -> IngestionResult:
        """
        Ingest a text document: chunk → embed → store.

        Args:
            user_id: Owner of the knowledge items.
            content: Full text content.
            title: Document title (used as metadata on each chunk).
            category: Knowledge category (e.g. "product", "finance", "legal").
            tags: Tags for filtering.
            source_url: Original URL (if applicable).
            metadata: Extra metadata dict.
        """
        start = time.time()
        doc_id = str(uuid.uuid4())

        # Build chunk metadata
        chunk_meta = {
            "document_id": doc_id,
            "title": title or "Untitled",
            **(metadata or {}),
        }

        # 1. Chunk
        chunks = self._chunker.chunk_text(content, metadata=chunk_meta)
        if not chunks:
            return IngestionResult(
                document_id=doc_id,
                chunks_created=0,
                total_tokens=0,
                knowledge_item_ids=[],
                duration_seconds=round(time.time() - start, 2),
                title=title,
                category=category,
            )

        # 2. Embed (in batches)
        embeddings = await self._batch_embed([c.text for c in chunks])

        # 3. Store
        item_ids = await self._store.bulk_upsert(
            user_id=user_id,
            items=[
                {
                    "content": chunk.text,
                    "embedding": emb,
                    "title": f"{title or 'Untitled'} (chunk {chunk.index + 1}/{len(chunks)})" if len(chunks) > 1 else title,
                    "category": category,
                    "tags": tags,
                    "source_url": source_url,
                    "content_type": "text_chunk",
                }
                for chunk, emb in zip(chunks, embeddings)
            ],
        )

        total_tokens = sum(c.token_count for c in chunks)

        logger.info(
            "Ingested document '%s': %d chunks, %d tokens",
            sl(title or doc_id), len(chunks), total_tokens,
        )

        return IngestionResult(
            document_id=doc_id,
            chunks_created=len(chunks),
            total_tokens=total_tokens,
            knowledge_item_ids=[str(id_) for id_ in item_ids],
            duration_seconds=round(time.time() - start, 2),
            title=title,
            category=category,
            source_url=source_url,
        )

    # ------------------------------------------------------------------
    # Ingest from URL
    # ------------------------------------------------------------------

    async def ingest_url(
        self,
        user_id: uuid.UUID,
        url: str,
        *,
        title: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
    ) -> IngestionResult:
        """
        Fetch a URL, extract text, and ingest it.

        Supports HTML pages (strips tags) and plain text.
        """
        # Fetch content
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        raw = response.text

        # Extract text from HTML
        if "html" in content_type:
            text_content = self._extract_text_from_html(raw)
        else:
            text_content = raw

        if not text_content.strip():
            raise ValueError(f"No extractable text content from URL: {url}")

        # Derive title from HTML if not provided
        if not title and "html" in content_type:
            title = self._extract_html_title(raw)

        return await self.ingest_text(
            user_id=user_id,
            content=text_content,
            title=title or url,
            category=category,
            tags=tags,
            source_url=url,
        )

    # ------------------------------------------------------------------
    # Ingest structured data
    # ------------------------------------------------------------------

    async def ingest_json(
        self,
        user_id: uuid.UUID,
        data: dict | list,
        *,
        title: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        key_fields: list[str] | None = None,
    ) -> IngestionResult:
        """
        Ingest structured JSON data.

        Flattens the structure into readable text, then processes normally.
        If key_fields is provided, extracts only those fields.
        """
        import json

        if isinstance(data, list):
            # Treat each item as a separate section
            sections: list[str] = []
            for i, item in enumerate(data):
                if isinstance(item, dict):
                    if key_fields:
                        item = {k: v for k, v in item.items() if k in key_fields}
                    sections.append(json.dumps(item, indent=2, default=str))
                else:
                    sections.append(str(item))
            text_content = "\n\n---\n\n".join(sections)
        elif isinstance(data, dict):
            if key_fields:
                data = {k: v for k, v in data.items() if k in key_fields}
            text_content = json.dumps(data, indent=2, default=str)
        else:
            text_content = str(data)

        return await self.ingest_text(
            user_id=user_id,
            content=text_content,
            title=title,
            category=category,
            tags=tags,
        )

    # ------------------------------------------------------------------
    # Batch ingest
    # ------------------------------------------------------------------

    async def ingest_batch(
        self,
        user_id: uuid.UUID,
        documents: list[dict],
    ) -> list[IngestionResult]:
        """
        Ingest multiple documents.

        Each dict should have:
          - content (str): text content
          - title (optional str)
          - category (optional str)
          - tags (optional list[str])
          - source_url (optional str)
        """
        results: list[IngestionResult] = []
        for doc in documents:
            result = await self.ingest_text(
                user_id=user_id,
                content=doc["content"],
                title=doc.get("title"),
                category=doc.get("category"),
                tags=doc.get("tags"),
                source_url=doc.get("source_url"),
            )
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _batch_embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts in batches to avoid overwhelming the provider."""
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i:i + EMBED_BATCH_SIZE]
            embeddings = await self._embedder.embed_batch(batch)
            all_embeddings.extend(embeddings)

        return all_embeddings

    @staticmethod
    def _extract_text_from_html(html: str) -> str:
        """Basic HTML → text extraction (no external dependency)."""
        # Remove script and style blocks
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<header[^>]*>.*?</header>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.DOTALL | re.IGNORECASE)

        # Convert block elements to newlines
        html = re.sub(r'<(?:p|div|h[1-6]|li|tr|br)[^>]*>', '\n', html, flags=re.IGNORECASE)

        # Strip all remaining tags
        text = re.sub(r'<[^>]+>', '', html)

        # Decode common HTML entities
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        text = text.replace('&#39;', "'")
        text = text.replace('&nbsp;', ' ')

        # Clean up whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)

        return text.strip()

    @staticmethod
    def _extract_html_title(html: str) -> str | None:
        """Extract <title> from HTML."""
        match = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None
