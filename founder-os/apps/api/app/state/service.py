"""StateService — the one sync entry point (arch §2.1), used by the Celery task.

Wires adapter ⇄ reconciler ⇄ mirror ⇄ renderer for a single source run:
observe → reconcile each event → render (ALL user entities — the unified
company model) → adapter.sync → update source status/report.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.integrations import registry
from app.state.models import CompanyStateEntity, StateRelation, StateSource
from app.state.reconciler import Reconciler
from app.state.renderer import render

logger = logging.getLogger(__name__)


def _provider_factory():
    """Lazy LLM provider for the write-gate judge (provider-neutral)."""
    from app.agents.llm import create_llm_provider

    settings = get_settings()
    api_key = {
        "anthropic": settings.ANTHROPIC_API_KEY,
        "openai_compatible": settings.OPENAI_API_KEY,
        "gemini": settings.GEMINI_API_KEY,
    }.get(settings.LLM_PROVIDER, "")
    base_url = {
        "ollama": settings.OLLAMA_BASE_URL,
        "openai_compatible": settings.OPENAI_BASE_URL,
    }.get(settings.LLM_PROVIDER, "")
    model = {
        "ollama": settings.OLLAMA_MODEL,
        "anthropic": settings.ANTHROPIC_MODEL,
        "openai_compatible": settings.OPENAI_MODEL,
        "gemini": settings.GEMINI_MODEL,
    }.get(settings.LLM_PROVIDER, "")
    return create_llm_provider(
        provider=settings.LLM_PROVIDER, api_key=api_key, base_url=base_url, model=model,
        openai_api_key=settings.OPENAI_API_KEY,
        openai_model=settings.OPENAI_MODEL or "gpt-4o-mini",
        openai_base_url=settings.OPENAI_BASE_URL or "https://api.openai.com/v1",
    )


class StateService:
    def __init__(self, db: AsyncSession, redis) -> None:
        self.db = db
        self.redis = redis

    async def run_sync(self, source_id: str, user_id: str, direction: str = "both") -> dict:
        """Run one sync for one source. Returns the sync report dict."""
        from app.integrations.obsidian.adapter import register_adapter

        register_adapter()  # idempotent; worker processes have no lifespan
        settings = get_settings()
        started = time.monotonic()

        source = (await self.db.execute(
            select(StateSource).where(
                StateSource.id == uuid.UUID(source_id),
                StateSource.user_id == uuid.UUID(user_id),
            )
        )).scalar_one_or_none()
        if source is None:
            raise ValueError("source not found for user")
        if source.status == "paused":
            raise ValueError("source is paused")

        adapter = registry.get(source.type)
        source.status = "syncing"
        await self.db.commit()

        report: dict = {}
        try:
            if direction in ("both", "inbound"):
                report.update(await self._inbound(source, adapter, settings))
            if direction in ("both", "outbound"):
                report.update(await self._outbound(source, adapter, user_id))
            report["duration_s"] = round(time.monotonic() - started, 2)
            source.status = "active"
            source.last_error = None
            source.last_synced_at = datetime.now(timezone.utc)
            source.last_sync_report = report
            await self.db.commit()
            return report
        except Exception as exc:
            await self.db.rollback()
            source.status = "error"
            source.last_error = str(exc)[:2000]
            await self.db.commit()
            raise

    async def _inbound(self, source: StateSource, adapter, settings) -> dict:
        from app.retrieval.chunker import TextChunker
        from app.retrieval.embeddings import get_default_embedder
        from app.retrieval.ingester import Ingester
        from app.retrieval.vector_store import VectorStore

        events = await adapter.observe_source(source.config, str(source.id))
        embedder = get_default_embedder(self.redis)
        ingester = Ingester(
            vector_store=VectorStore(self.db),
            embedder=embedder,
            chunker=TextChunker(),
        )
        reconciler = Reconciler(
            db=self.db,
            user_id=source.user_id,
            source_id=source.id,
            embedder=embedder,
            ingester=ingester,
            provider_factory=_provider_factory,
            sim_threshold=settings.STATE_DEDUP_SIM_THRESHOLD,
            judge_max_calls=settings.STATE_WRITE_GATE_JUDGE_MAX_PER_SYNC,
            judge_timeout_s=settings.STATE_WRITE_GATE_JUDGE_TIMEOUT_S,
        )
        for event in events:
            await reconciler.reconcile_event(event)
        return reconciler.counters.as_dict()

    async def _outbound(self, source: StateSource, adapter, user_id: str) -> dict:
        entities = list((await self.db.execute(
            select(CompanyStateEntity).where(
                CompanyStateEntity.user_id == uuid.UUID(user_id),
                CompanyStateEntity.is_active.is_(True),
            )
        )).scalars())
        relations = list((await self.db.execute(
            select(StateRelation).where(StateRelation.user_id == uuid.UUID(user_id))
        )).scalars())

        files = render(entities, relations, now=datetime.now(timezone.utc))
        result = await adapter.sync(user_id, [{"config": source.config, "files": files}])
        if not result.ok:
            raise RuntimeError(f"outbound sync failed: {result.errors}")
        return {"rendered_files": len(files)}
