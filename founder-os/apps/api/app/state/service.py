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

    async def run_sync(self, source_id: str, user_id: str, direction: str = "both",
                       full_walk: bool = False) -> dict:
        """Run one sync for one source. Returns the sync report dict."""
        from app.integrations.notion.adapter import register_adapter as register_notion
        from app.integrations.obsidian.adapter import register_adapter as register_obsidian

        register_obsidian()  # idempotent; worker processes have no lifespan
        register_notion()
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
            credentials = await self._credentials_for(source)
            if direction in ("both", "inbound"):
                report.update(await self._inbound(source, adapter, settings,
                                                  credentials=credentials,
                                                  full_walk=full_walk))
            if direction in ("both", "outbound"):
                report.update(await self._outbound(source, adapter, user_id,
                                                   credentials=credentials))
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

    async def _credentials_for(self, source: StateSource) -> dict:
        from app.integrations.credentials import resolve_source_credentials

        return await resolve_source_credentials(self.db, source)

    async def _seen_notion_uuids(self, source: StateSource) -> set[str]:
        """Seen-set from the DB, not the cursor (arch §1): distinct page uuids
        this source has fed into ACTIVE entities — the full-walk diff input."""
        from sqlalchemy import text as sql_text

        rows = (await self.db.execute(sql_text("""
            SELECT DISTINCT o.external_id
            FROM state_observations o
            JOIN company_state_entities e ON e.id = o.entity_id
            WHERE o.source_id = :sid AND e.is_active = true
        """), {"sid": str(source.id)})).fetchall()
        out: set[str] = set()
        for (eid,) in rows:
            parts = eid.split(":")
            if len(parts) == 4 and parts[2] == "page":
                out.add(parts[3])
        return out

    async def _inbound(self, source: StateSource, adapter, settings, *,
                       credentials: dict, full_walk: bool = False) -> dict:
        from app.retrieval.chunker import TextChunker
        from app.retrieval.embeddings import get_default_embedder
        from app.retrieval.ingester import Ingester
        from app.retrieval.vector_store import VectorStore

        kwargs: dict = {
            "credentials": credentials,
            "sync_cursor": source.sync_cursor,
            "full_walk": full_walk,
        }
        if source.type == "notion":
            kwargs["seen_external_uuids"] = await self._seen_notion_uuids(source)
        observed = await adapter.observe_source(source.config, str(source.id), **kwargs)
        # D4: notion returns (events, new_cursor); obsidian returns a bare list
        new_cursor_fields: dict = {}
        if isinstance(observed, tuple):
            events, new_cursor_fields = observed
        else:
            events = observed
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

        report = reconciler.counters.as_dict()
        if new_cursor_fields:
            api_counters = new_cursor_fields.pop("_counters", {})
            report.update(api_counters)
            # cursor persists ONLY after a successful inbound pass (arch §6)
            cursor = dict(source.sync_cursor or {})
            cursor.update(new_cursor_fields)
            source.sync_cursor = cursor
            await self.db.flush()
        return report

    async def _outbound(self, source: StateSource, adapter, user_id: str, *,
                        credentials: dict) -> dict:
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
        change: dict = {"config": source.config, "files": files}
        if source.type == "notion":
            change["credentials"] = credentials
            change["ledger"] = (source.sync_cursor or {}).get("managed_pages") or {}
        result = await adapter.sync(user_id, [change])
        if not result.ok:
            raise RuntimeError(f"outbound sync failed: {result.errors}")
        report = {"rendered_files": len(files)}
        if result.data:
            # D5: adapter returns the updated ledger; the SERVICE persists it
            ledger = result.data.pop("managed_pages", None)
            report.update(result.data)
            if ledger is not None:
                cursor = dict(source.sync_cursor or {})
                cursor["managed_pages"] = ledger
                source.sync_cursor = cursor
                await self.db.flush()
        return report
