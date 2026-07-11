"""
Founder OS — Embedding Provider
=================================
Multi-backend embedding generation, mirroring the LLM provider pattern.

Supported backends:
  - **Ollama**  (free, local) — nomic-embed-text, all-minilm, mxbai-embed-large, etc.
  - **OpenAI-compatible** — text-embedding-3-small/large, or any /v1/embeddings API
    (also works with Together, Voyage, Jina, Fireworks, etc.)

All providers normalise to ``list[float]`` with configurable dimensions.
Embeddings are cached in Redis with a content-hash key to avoid redundant calls.
"""

from __future__ import annotations

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

import httpx
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Default models per provider
OLLAMA_DEFAULT_MODEL = "nomic-embed-text"
OPENAI_DEFAULT_MODEL = "text-embedding-3-small"

# Cache TTL — 7 days (embeddings don't change for the same content)
EMBEDDING_CACHE_TTL = 60 * 60 * 24 * 7


@dataclass
class EmbeddingResult:
    """Result of an embedding call."""
    embedding: list[float]
    model: str
    dimensions: int
    tokens_used: int = 0
    cached: bool = False


# ============================================================================
# Abstract base
# ============================================================================

class EmbeddingProvider(ABC):
    """Abstract embedding provider interface."""

    model: str = ""
    dimensions: int = 1536

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for a single text."""
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts in one call."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources."""
        ...


# ============================================================================
# Ollama Embeddings (free, local)
# ============================================================================

class OllamaEmbeddings(EmbeddingProvider):
    """
    Generate embeddings using Ollama's local models.

    Popular models:
      - nomic-embed-text (768d) — best quality/speed ratio
      - all-minilm (384d) — fastest, decent quality
      - mxbai-embed-large (1024d) — highest quality
    """

    DIMENSION_MAP = {
        "nomic-embed-text": 768,
        "all-minilm": 384,
        "mxbai-embed-large": 1024,
        "snowflake-arctic-embed": 1024,
    }

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = OLLAMA_DEFAULT_MODEL,
    ) -> None:
        self.model = model
        self._base_url = base_url.rstrip("/")
        self.dimensions = self.DIMENSION_MAP.get(model, 768)
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    async def embed(self, text: str) -> list[float]:
        """Generate a single embedding via Ollama."""
        response = await self._client.post(
            "/api/embed",
            json={"model": self.model, "input": text},
        )
        response.raise_for_status()
        data = response.json()

        # Ollama returns {"embeddings": [[...]], "model": "..."}
        embeddings = data.get("embeddings", [])
        if not embeddings:
            raise ValueError(f"Ollama returned empty embeddings for model {self.model}")

        vec = embeddings[0]
        return self._pad_or_truncate(vec)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Ollama's /api/embed supports batch input natively."""
        if not texts:
            return []

        response = await self._client.post(
            "/api/embed",
            json={"model": self.model, "input": texts},
        )
        response.raise_for_status()
        data = response.json()

        embeddings = data.get("embeddings", [])
        return [self._pad_or_truncate(vec) for vec in embeddings]

    def _pad_or_truncate(self, vec: list[float]) -> list[float]:
        """Ensure vector matches our target 1536 dimensions via zero-padding."""
        if len(vec) == 1536:
            return vec
        if len(vec) > 1536:
            return vec[:1536]
        # Zero-pad to 1536 for pgvector compatibility
        return vec + [0.0] * (1536 - len(vec))

    async def close(self) -> None:
        await self._client.aclose()


# ============================================================================
# OpenAI-compatible Embeddings
# ============================================================================

class OpenAIEmbeddings(EmbeddingProvider):
    """
    Generate embeddings via any OpenAI-compatible /v1/embeddings API.

    Works with:
      - OpenAI (text-embedding-3-small / text-embedding-3-large)
      - Together AI
      - Voyage AI (via OpenAI-compat endpoint)
      - Jina AI
      - Fireworks
      - Any /v1/embeddings provider
    """

    DIMENSION_MAP = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = OPENAI_DEFAULT_MODEL,
        dimensions: int | None = None,
    ) -> None:
        self.model = model
        self._base_url = base_url.rstrip("/")
        self.dimensions = dimensions or self.DIMENSION_MAP.get(model, 1536)
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    async def embed(self, text: str) -> list[float]:
        """Generate a single embedding via the OpenAI embeddings API."""
        response = await self._client.post(
            "/embeddings",
            json={
                "model": self.model,
                "input": text,
                "encoding_format": "float",
            },
        )
        response.raise_for_status()
        data = response.json()

        vec = data["data"][0]["embedding"]
        return self._pad_or_truncate(vec)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch embedding — OpenAI API supports array input natively."""
        if not texts:
            return []

        response = await self._client.post(
            "/embeddings",
            json={
                "model": self.model,
                "input": texts,
                "encoding_format": "float",
            },
        )
        response.raise_for_status()
        data = response.json()

        # Sort by index to maintain order
        sorted_data = sorted(data["data"], key=lambda x: x["index"])
        return [self._pad_or_truncate(item["embedding"]) for item in sorted_data]

    def _pad_or_truncate(self, vec: list[float]) -> list[float]:
        """Normalise to 1536 dimensions for pgvector."""
        if len(vec) == 1536:
            return vec
        if len(vec) > 1536:
            return vec[:1536]
        return vec + [0.0] * (1536 - len(vec))

    async def close(self) -> None:
        await self._client.aclose()


# ============================================================================
# Cached wrapper
# ============================================================================

class CachedEmbeddingProvider(EmbeddingProvider):
    """
    Redis-cached wrapper around any EmbeddingProvider.
    Caches embeddings by content hash to avoid redundant API calls.
    """

    def __init__(
        self,
        provider: EmbeddingProvider,
        redis: aioredis.Redis,
        ttl: int = EMBEDDING_CACHE_TTL,
    ) -> None:
        self._provider = provider
        self._redis = redis
        self._ttl = ttl
        self.model = provider.model
        self.dimensions = provider.dimensions

    def _cache_key(self, text: str) -> str:
        content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        return f"emb_cache:{self.model}:{content_hash}"

    async def embed(self, text: str) -> list[float]:
        key = self._cache_key(text)
        cached = await self._redis.get(key)
        if cached is not None:
            return json.loads(cached)

        vec = await self._provider.embed(text)
        await self._redis.set(key, json.dumps(vec), ex=self._ttl)
        return vec

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        # Check cache for each text
        keys = [self._cache_key(t) for t in texts]
        cached_values = await self._redis.mget(keys)

        results: list[list[float] | None] = []
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        for i, (text, cached) in enumerate(zip(texts, cached_values)):
            if cached is not None:
                results.append(json.loads(cached))
            else:
                results.append(None)
                uncached_indices.append(i)
                uncached_texts.append(text)

        # Embed uncached texts in a batch
        if uncached_texts:
            new_embeddings = await self._provider.embed_batch(uncached_texts)
            pipe = self._redis.pipeline()
            for idx, vec in zip(uncached_indices, new_embeddings):
                results[idx] = vec
                pipe.set(keys[idx], json.dumps(vec), ex=self._ttl)
            await pipe.execute()

        return results  # type: ignore[return-value]

    async def close(self) -> None:
        await self._provider.close()


# ============================================================================
# Factory
# ============================================================================

def create_embedding_provider(
    provider: str = "ollama",
    api_key: str = "",
    base_url: str = "",
    model: str = "",
    redis: aioredis.Redis | None = None,
) -> EmbeddingProvider:
    """
    Create an embedding provider from configuration.

    Args:
        provider: "ollama" | "openai" | "openai_compatible"
        api_key: API key (for OpenAI-compatible)
        base_url: Override the base URL
        model: Override the model name
        redis: Optional Redis client for caching

    Returns:
        Configured EmbeddingProvider (optionally cached)
    """
    if provider == "ollama":
        base = OllamaEmbeddings(
            base_url=base_url or "http://localhost:11434",
            model=model or OLLAMA_DEFAULT_MODEL,
        )
    elif provider in ("openai", "openai_compatible"):
        if not api_key:
            raise ValueError("OpenAI-compatible embeddings require an API key")
        base = OpenAIEmbeddings(
            api_key=api_key,
            base_url=base_url or "https://api.openai.com/v1",
            model=model or OPENAI_DEFAULT_MODEL,
        )
    else:
        raise ValueError(f"Unknown embedding provider: {provider}")

    if redis:
        return CachedEmbeddingProvider(base, redis)

    return base


def get_default_embedder(redis: aioredis.Redis | None = None) -> EmbeddingProvider:
    """Settings-driven default embedder (arch 2026-07-04 §2.4).

    Replicates the provider-selection logic of knowledge_routes._get_embedder so
    non-route modules (app/state/*) never import a route module. Converge the
    route helper onto this factory later.
    """
    from app.config import get_settings  # local import: avoid config↔retrieval cycle

    settings = get_settings()
    # EMBEDDING_* settings decide — NOT LLM_PROVIDER. Chat and embeddings are
    # independent axes: e.g. LLM on Groq (openai_compatible) has NO embeddings
    # endpoint, so embeddings stay on Ollama/OpenAI (founder Groq switch,
    # 2026-07-11). Mirrors app/agents/registry.py's embedder selection.
    if settings.EMBEDDING_PROVIDER == "openai":
        return create_embedding_provider(
            provider="openai",
            api_key=settings.EMBEDDING_API_KEY or settings.OPENAI_API_KEY,
            base_url=settings.EMBEDDING_BASE_URL or "https://api.openai.com/v1",
            model=settings.EMBEDDING_MODEL or "",
            redis=redis,
        )
    return create_embedding_provider(
        provider="ollama",
        base_url=settings.EMBEDDING_BASE_URL or settings.OLLAMA_BASE_URL,
        model=settings.EMBEDDING_MODEL or "",
        redis=redis,
    )
