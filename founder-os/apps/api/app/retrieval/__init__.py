"""
Founder OS — Context Retrieval System
=======================================
Vector DB (pgvector) powered RAG pipeline for agent context augmentation.

Components:
  - **EmbeddingProvider** — multi-backend embeddings (Ollama, OpenAI, Anthropic-via-Voyage)
  - **VectorStore**       — pgvector CRUD + hybrid search (semantic + full-text)
  - **Chunker**           — token-aware document splitting
  - **Ingester**          — document ingestion pipeline (text, URL, file)
  - **ContextRetriever**  — high-level retrieval with re-ranking + context formatting

Usage:
    from app.retrieval import ContextRetriever, Ingester, EmbeddingProvider

    embedder = EmbeddingProvider.from_settings(settings)
    retriever = ContextRetriever(db=session, embedder=embedder, user_id=uid)

    # Ingest a document
    ingester = Ingester(db=session, embedder=embedder)
    await ingester.ingest_text(user_id=uid, title="Product Roadmap", content=text)

    # Retrieve context for an agent
    results = await retriever.search("What's our pricing strategy?", limit=5)
"""

from app.retrieval.embeddings import (
    EmbeddingProvider,
    OllamaEmbeddings,
    OpenAIEmbeddings,
    create_embedding_provider,
)
from app.retrieval.vector_store import VectorStore, SearchResult
from app.retrieval.chunker import TextChunker, Chunk
from app.retrieval.ingester import Ingester, IngestionResult
from app.retrieval.retriever import ContextRetriever, RetrievalResult

__all__ = [
    # Embeddings
    "EmbeddingProvider",
    "OllamaEmbeddings",
    "OpenAIEmbeddings",
    "create_embedding_provider",
    # Vector Store
    "VectorStore",
    "SearchResult",
    # Chunker
    "TextChunker",
    "Chunk",
    # Ingestion
    "Ingester",
    "IngestionResult",
    # Retrieval
    "ContextRetriever",
    "RetrievalResult",
]
