"""
Founder OS — Knowledge & Retrieval API Routes
================================================
Endpoints for managing the knowledge base and performing context retrieval.

Routes:
    POST   /api/knowledge/ingest/text    — Ingest plain text
    POST   /api/knowledge/ingest/url     — Ingest from URL
    POST   /api/knowledge/ingest/json    — Ingest structured JSON
    POST   /api/knowledge/ingest/batch   — Batch ingest multiple docs
    POST   /api/knowledge/search         — Search knowledge base
    GET    /api/knowledge/stats          — Knowledge base stats
    GET    /api/knowledge/items          — List knowledge items
    GET    /api/knowledge/items/{id}     — Get a single item
    DELETE /api/knowledge/items/{id}     — Delete a knowledge item
    DELETE /api/knowledge/items          — Delete all (with filters)
"""

from __future__ import annotations

import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ClerkUser, require_auth
from app.config import get_settings
from app.database import get_db
from app.models import KnowledgeItem
from app.redis import get_redis
from app.retrieval.embeddings import create_embedding_provider
from app.retrieval.vector_store import VectorStore
from app.retrieval.chunker import TextChunker
from app.retrieval.ingester import Ingester
from app.retrieval.retriever import ContextRetriever

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


# ── Helpers ───────────────────────────────────────────────────

def _get_embedder(settings=None):
    """Create an embedding provider from app settings."""
    settings = settings or get_settings()
    redis = get_redis()

    # Use the same provider as the LLM, but for embeddings
    if settings.LLM_PROVIDER == "ollama":
        return create_embedding_provider(
            provider="ollama",
            base_url=settings.OLLAMA_BASE_URL,
            redis=redis,
        )
    elif settings.LLM_PROVIDER == "openai_compatible":
        return create_embedding_provider(
            provider="openai",
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            redis=redis,
        )
    elif settings.LLM_PROVIDER == "anthropic":
        # Anthropic doesn't have embeddings — fall back to Ollama if available
        # or OpenAI if key is set
        if settings.OPENAI_API_KEY:
            return create_embedding_provider(
                provider="openai",
                api_key=settings.OPENAI_API_KEY,
                redis=redis,
            )
        return create_embedding_provider(
            provider="ollama",
            base_url=settings.OLLAMA_BASE_URL,
            redis=redis,
        )
    else:
        return create_embedding_provider(provider="ollama", redis=redis)


def _user_uuid(user: ClerkUser) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"clerk:{user.user_id}")


# ── Request / Response Models ─────────────────────────────────

class IngestTextRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=500000)
    title: str | None = Field(None, max_length=500)
    category: str | None = Field(None, max_length=100)
    tags: list[str] | None = None
    source_url: str | None = None
    chunk_size: int = Field(512, ge=64, le=2048, description="Target tokens per chunk")
    chunk_overlap: int = Field(50, ge=0, le=512, description="Overlap tokens between chunks")


class IngestURLRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    title: str | None = Field(None, max_length=500)
    category: str | None = Field(None, max_length=100)
    tags: list[str] | None = None


class IngestJSONRequest(BaseModel):
    data: dict | list = Field(...)
    title: str | None = Field(None, max_length=500)
    category: str | None = Field(None, max_length=100)
    tags: list[str] | None = None
    key_fields: list[str] | None = None


class BatchIngestRequest(BaseModel):
    documents: list[dict] = Field(..., min_length=1, max_length=50)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)
    limit: int = Field(5, ge=1, le=50)
    min_similarity: float = Field(0.5, ge=0.0, le=1.0)
    category: str | None = None
    tags: list[str] | None = None
    search_type: str = Field("hybrid", description="hybrid | semantic | fulltext | mmr")


class IngestionResponse(BaseModel):
    document_id: str
    chunks_created: int
    total_tokens: int
    knowledge_item_ids: list[str]
    duration_seconds: float
    title: str | None = None
    category: str | None = None
    source_url: str | None = None


class SearchResultResponse(BaseModel):
    id: str
    title: str | None
    content: str
    category: str | None
    tags: list[str] | None
    score: float
    source_url: str | None = None


class SearchResponse(BaseModel):
    results: list[SearchResultResponse]
    query: str
    search_type: str
    total_results: int


class KnowledgeItemResponse(BaseModel):
    id: str
    title: str | None
    content: str
    content_type: str | None
    category: str | None
    tags: list[str] | None
    source_url: str | None
    has_embedding: bool
    times_referenced: int
    processing_status: str
    created_at: str


class KnowledgeStatsResponse(BaseModel):
    total_items: int
    items_with_embeddings: int
    items_without_embeddings: int
    embedding_model: str
    embedding_dimensions: int


# ── Routes ────────────────────────────────────────────────────

@router.post("/ingest/text", response_model=IngestionResponse, status_code=201)
async def ingest_text(
    body: IngestTextRequest,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Ingest plain text into the knowledge base."""
    embedder = _get_embedder()
    store = VectorStore(db)
    chunker = TextChunker(chunk_size=body.chunk_size, chunk_overlap=body.chunk_overlap)
    ingester = Ingester(vector_store=store, embedder=embedder, chunker=chunker)

    try:
        result = await ingester.ingest_text(
            user_id=_user_uuid(user),
            content=body.content,
            title=body.title,
            category=body.category,
            tags=body.tags,
            source_url=body.source_url,
        )
    finally:
        await embedder.close()

    return IngestionResponse(
        document_id=result.document_id,
        chunks_created=result.chunks_created,
        total_tokens=result.total_tokens,
        knowledge_item_ids=result.knowledge_item_ids,
        duration_seconds=result.duration_seconds,
        title=result.title,
        category=result.category,
        source_url=result.source_url,
    )


@router.post("/ingest/url", response_model=IngestionResponse, status_code=201)
async def ingest_url(
    body: IngestURLRequest,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Fetch content from a URL and ingest it into the knowledge base."""
    embedder = _get_embedder()
    store = VectorStore(db)
    ingester = Ingester(vector_store=store, embedder=embedder)

    try:
        result = await ingester.ingest_url(
            user_id=_user_uuid(user),
            url=body.url,
            title=body.title,
            category=body.category,
            tags=body.tags,
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch URL: {exc}")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        await embedder.close()

    return IngestionResponse(
        document_id=result.document_id,
        chunks_created=result.chunks_created,
        total_tokens=result.total_tokens,
        knowledge_item_ids=result.knowledge_item_ids,
        duration_seconds=result.duration_seconds,
        title=result.title,
        category=result.category,
        source_url=result.source_url,
    )


@router.post("/ingest/json", response_model=IngestionResponse, status_code=201)
async def ingest_json(
    body: IngestJSONRequest,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Ingest structured JSON data into the knowledge base."""
    embedder = _get_embedder()
    store = VectorStore(db)
    ingester = Ingester(vector_store=store, embedder=embedder)

    try:
        result = await ingester.ingest_json(
            user_id=_user_uuid(user),
            data=body.data,
            title=body.title,
            category=body.category,
            tags=body.tags,
            key_fields=body.key_fields,
        )
    finally:
        await embedder.close()

    return IngestionResponse(
        document_id=result.document_id,
        chunks_created=result.chunks_created,
        total_tokens=result.total_tokens,
        knowledge_item_ids=result.knowledge_item_ids,
        duration_seconds=result.duration_seconds,
        title=result.title,
        category=result.category,
    )


@router.post("/ingest/batch", response_model=list[IngestionResponse], status_code=201)
async def ingest_batch(
    body: BatchIngestRequest,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Batch ingest multiple documents at once (max 50)."""
    embedder = _get_embedder()
    store = VectorStore(db)
    ingester = Ingester(vector_store=store, embedder=embedder)

    try:
        results = await ingester.ingest_batch(
            user_id=_user_uuid(user),
            documents=body.documents,
        )
    finally:
        await embedder.close()

    return [
        IngestionResponse(
            document_id=r.document_id,
            chunks_created=r.chunks_created,
            total_tokens=r.total_tokens,
            knowledge_item_ids=r.knowledge_item_ids,
            duration_seconds=r.duration_seconds,
            title=r.title,
            category=r.category,
            source_url=r.source_url,
        )
        for r in results
    ]


# ── Allowed MIME types for file upload ─────────────────────────
_ALLOWED_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/pdf",
    "application/json",
}

_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/ingest/file", response_model=IngestionResponse, status_code=201)
async def ingest_file(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    category: str | None = Form(None),
    tags: str | None = Form(None, description="Comma-separated tags"),
    chunk_size: int = Form(512),
    chunk_overlap: int = Form(50),
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a file and ingest its content into the knowledge base.

    Supported formats: .txt, .md, .csv, .json, .pdf (text-based).
    Max file size: 10 MB.
    """
    # Validate file type
    content_type = file.content_type or ""
    filename = file.filename or "upload"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    allowed_extensions = {"txt", "md", "csv", "json", "pdf"}
    if ext not in allowed_extensions and content_type not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {ext or content_type}. "
                   f"Allowed: {', '.join(sorted(allowed_extensions))}",
        )

    # Read file content with size limit
    raw = await file.read()
    if len(raw) > _MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Max 10 MB.")

    # Extract text based on file type
    if ext == "pdf":
        # Basic PDF text extraction — requires pdfplumber or fallback
        try:
            import pdfplumber
            import io
            text = ""
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n\n"
        except ImportError:
            raise HTTPException(
                status_code=501,
                detail="PDF support requires pdfplumber. Install with: pip install pdfplumber",
            )
        if not text.strip():
            raise HTTPException(status_code=422, detail="Could not extract text from PDF.")
    elif ext == "json":
        import json as _json
        try:
            data = _json.loads(raw.decode("utf-8"))
            text = _json.dumps(data, indent=2, ensure_ascii=False)
        except (UnicodeDecodeError, _json.JSONDecodeError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid JSON file: {exc}")
    else:
        # Plain text / markdown / CSV
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")

    if not text.strip():
        raise HTTPException(status_code=422, detail="File is empty or contains no extractable text.")

    # Parse tags
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

    # Ingest
    embedder = _get_embedder()
    store = VectorStore(db)
    chunker = TextChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    ingester = Ingester(vector_store=store, embedder=embedder, chunker=chunker)

    try:
        result = await ingester.ingest_text(
            user_id=_user_uuid(user),
            content=text,
            title=title or filename,
            category=category,
            tags=tag_list,
            source_url=f"file://{filename}",
        )
    finally:
        await embedder.close()

    return IngestionResponse(
        document_id=result.document_id,
        chunks_created=result.chunks_created,
        total_tokens=result.total_tokens,
        knowledge_item_ids=result.knowledge_item_ids,
        duration_seconds=result.duration_seconds,
        title=result.title or filename,
        category=result.category,
        source_url=f"file://{filename}",
    )


@router.post("/search", response_model=SearchResponse)
async def search_knowledge(
    body: SearchRequest,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """
    Search the knowledge base using semantic, full-text, or hybrid search.

    Hybrid search (default) combines cosine similarity with full-text ranking
    using Reciprocal Rank Fusion for the best results.
    """
    embedder = _get_embedder()
    retriever = ContextRetriever(db=db, embedder=embedder, user_id=_user_uuid(user))

    try:
        results = await retriever.search(
            body.query,
            limit=body.limit,
            min_similarity=body.min_similarity,
            category=body.category,
            tags=body.tags,
            search_type=body.search_type,
        )
    finally:
        await embedder.close()

    return SearchResponse(
        results=[
            SearchResultResponse(
                id=str(r.id),
                title=r.title,
                content=r.content,
                category=r.category,
                tags=r.tags,
                score=round(r.score, 4),
                source_url=r.source_url,
            )
            for r in results
        ],
        query=body.query,
        search_type=body.search_type,
        total_results=len(results),
    )


@router.get("/stats", response_model=KnowledgeStatsResponse)
async def knowledge_stats(
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get knowledge base statistics for the authenticated user."""
    embedder = _get_embedder()
    retriever = ContextRetriever(db=db, embedder=embedder, user_id=_user_uuid(user))

    try:
        stats = await retriever.get_stats()
    finally:
        await embedder.close()

    return KnowledgeStatsResponse(**stats)


@router.get("/items", response_model=list[KnowledgeItemResponse])
async def list_knowledge_items(
    category: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """List knowledge items for the authenticated user."""
    uid = _user_uuid(user)
    stmt = (
        select(KnowledgeItem)
        .where(KnowledgeItem.user_id == uid, KnowledgeItem.is_active == True)
        .order_by(KnowledgeItem.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if category:
        stmt = stmt.where(KnowledgeItem.category == category)

    result = await db.execute(stmt)
    items = result.scalars().all()

    return [
        KnowledgeItemResponse(
            id=str(item.id),
            title=item.title,
            content=item.content[:500],  # truncate for listing
            content_type=item.content_type,
            category=item.category,
            tags=item.tags,
            source_url=item.source_url,
            has_embedding=item.embedding is not None,
            times_referenced=item.times_referenced,
            processing_status=item.processing_status,
            created_at=item.created_at.isoformat(),
        )
        for item in items
    ]


@router.get("/items/{item_id}", response_model=KnowledgeItemResponse)
async def get_knowledge_item(
    item_id: uuid.UUID,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get a single knowledge item."""
    uid = _user_uuid(user)
    item = await db.get(KnowledgeItem, item_id)

    if not item or item.user_id != uid:
        raise HTTPException(status_code=404, detail="Knowledge item not found")

    return KnowledgeItemResponse(
        id=str(item.id),
        title=item.title,
        content=item.content,  # full content for single item
        content_type=item.content_type,
        category=item.category,
        tags=item.tags,
        source_url=item.source_url,
        has_embedding=item.embedding is not None,
        times_referenced=item.times_referenced,
        processing_status=item.processing_status,
        created_at=item.created_at.isoformat(),
    )


@router.delete("/items/{item_id}", status_code=204)
async def delete_knowledge_item(
    item_id: uuid.UUID,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single knowledge item."""
    uid = _user_uuid(user)
    store = VectorStore(db)

    item = await db.get(KnowledgeItem, item_id)
    if not item or item.user_id != uid:
        raise HTTPException(status_code=404, detail="Knowledge item not found")

    await store.delete(item_id)


@router.delete("/items", status_code=200)
async def delete_knowledge_items(
    category: str | None = Query(None, description="Delete only items in this category"),
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Delete all knowledge items for the user (optionally filtered by category)."""
    uid = _user_uuid(user)
    store = VectorStore(db)
    count = await store.delete_by_user(uid, category=category)
    return {"deleted": count, "category": category}
