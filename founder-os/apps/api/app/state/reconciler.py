"""The reconciler (arch §2.2): ObservedEvent list → canonical entities/relations.

Per-event pipeline: observation insert (idempotent) → hard resolution →
write-gate → dedup → create/merge → relations → RAG mirror → audit outcome.
One commit per event so a mid-sync crash leaves consistent per-event state.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.base import ObservedEvent
from app.state import dedup as dedup_mod
from app.state import mirror as mirror_mod
from app.state import write_gate
from app.state.models import CompanyStateEntity, StateObservation, StateRelation

logger = logging.getLogger(__name__)


def canonical_content_hash(payload: dict) -> str:
    """sha256 of the canonicalized payload (arch §1.3) — stable across dict order."""
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


@dataclass
class SyncCounters:
    observed: int = 0
    unchanged: int = 0
    created: int = 0
    merged: int = 0
    updated: int = 0
    gated: int = 0
    mirrored: int = 0
    archived: int = 0   # D1 (Phase 2): tombstone transitions
    errors: int = 0
    judge_calls: int = 0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def is_tombstone(payload: dict) -> bool:
    """D1: 'the source says gone' — a payload contract, not a Notion special case."""
    return bool(payload.get("tombstone"))


@dataclass
class Reconciler:
    db: AsyncSession
    user_id: uuid.UUID
    source_id: uuid.UUID
    embedder: object            # EmbeddingProvider
    ingester: object            # retrieval Ingester (for the mirror)
    provider_factory: object    # () -> LLM provider, built lazily on first borderline
    sim_threshold: float
    judge_max_calls: int
    judge_timeout_s: float
    counters: SyncCounters = field(default_factory=SyncCounters)
    # external_id → entity_id within this run (relation hints resolve locally first)
    _run_entities: dict = field(default_factory=dict)
    _provider: object = None

    # ── pipeline ─────────────────────────────────────────────────────────

    async def reconcile_event(self, event: ObservedEvent) -> None:
        self.counters.observed += 1
        try:
            content_hash = canonical_content_hash(event.payload)
            inserted = await self._insert_observation(event, content_hash)
            if inserted is None:  # ON CONFLICT DO NOTHING hit → unchanged
                self.counters.unchanged += 1
                return

            if is_tombstone(event.payload):
                await self._apply_tombstone(event, inserted)
                await self.db.commit()
                return

            entity = await self._resolve_hard(event)
            outcome = None
            if entity is not None:
                # Hard resolution = same external identity → retitle is truth (D2)
                changes = dedup_mod.merge(entity, _as_candidate(event), inserted,
                                          hard_match=True)
                # Reactivation (D1): a normal event NEWER than the archival
                # restores it; stale re-walks never resurrect.
                if not entity.is_active and event.observed_at > entity.last_asserted_at:
                    changes["is_active"] = True
                await self._apply_changes(entity, changes)
                outcome = "updated"
                self.counters.updated += 1
            else:
                gate_result = await self._gate(event)
                if gate_result is None:  # rejected
                    outcome = "gated"
                    self.counters.gated += 1
                    await self._finish_observation(inserted, outcome, None)
                    await self.db.commit()
                    return
                confidence = gate_result
                entity, outcome = await self._dedup_or_create(event, inserted, confidence)

            self._run_entities[event.external_id] = entity.id
            await self._upsert_relations(event, entity)

            if await mirror_mod.mirror_entity(
                self.db, self.ingester,
                user_id=self.user_id, source_id=self.source_id,
                external_id=event.external_id, kind=event.kind,
                title=event.payload.get("title", ""),
                # B1: mirror the FULL body (arch §7 "note and decision bodies");
                # summary is only the display fallback.
                body=event.payload.get("body") or event.payload.get("summary") or "",
            ):
                self.counters.mirrored += 1

            await self._finish_observation(inserted, outcome, entity.id)
            await self.db.commit()
        except Exception:
            self.counters.errors += 1
            await self.db.rollback()
            logger.exception("reconcile failed for %s", event.external_id)

    # ── steps ────────────────────────────────────────────────────────────

    async def _apply_tombstone(self, event: ObservedEvent, observation_row) -> None:
        """D1: source says gone. Trail-only resolution (never title-match — too
        risky for a destructive transition); gated-never-created ids are a
        clean no-op (arch §13)."""
        entity_id = await self._resolve_hint(event.external_id)
        if entity_id is None:
            await self._finish_observation(observation_row, "archived", None)
            self.counters.archived += 1
            return
        entity = await self.db.get(CompanyStateEntity, entity_id)
        if entity is not None and entity.user_id == self.user_id:
            entity.is_active = False
            if entity.entity_type != "task":
                entity.status = "archived"
            await self.db.flush()
            await mirror_mod.purge_mirror(
                self.db, user_id=self.user_id, source_id=self.source_id,
                external_id=event.external_id,
            )
        await self._finish_observation(observation_row, "archived", entity_id)
        self.counters.archived += 1

    async def _insert_observation(self, event: ObservedEvent, content_hash: str):
        row = (await self.db.execute(
            text("""
                INSERT INTO state_observations
                    (source_id, user_id, external_id, kind, payload, content_hash,
                     provenance, observed_at)
                VALUES (:sid, :uid, :eid, :kind, CAST(:payload AS jsonb), :hash,
                        :prov, :at)
                ON CONFLICT (source_id, external_id, content_hash) DO NOTHING
                RETURNING id, observed_at, source_id
            """),
            {
                "sid": str(self.source_id), "uid": str(self.user_id),
                "eid": event.external_id, "kind": event.kind,
                "payload": json.dumps(event.payload, default=str),
                "hash": content_hash, "prov": event.provenance,
                "at": event.observed_at,
            },
        )).fetchone()
        return row

    async def _resolve_hard(self, event: ObservedEvent) -> CompanyStateEntity | None:
        # (a) latest prior observation with same (source_id, external_id) that fed an entity
        row = (await self.db.execute(
            text("""
                SELECT entity_id FROM state_observations
                WHERE source_id = :sid AND external_id = :eid AND entity_id IS NOT NULL
                ORDER BY observed_at DESC LIMIT 1
            """),
            {"sid": str(self.source_id), "eid": event.external_id},
        )).fetchone()
        if row and row.entity_id:
            return await self.db.get(CompanyStateEntity, row.entity_id)
        # (b) exact-title match: same user + type, casefolded/ws-collapsed
        title_norm = " ".join(str(event.payload.get("title", "")).split()).casefold()
        if not title_norm:
            return None
        result = await self.db.execute(
            select(CompanyStateEntity).where(
                CompanyStateEntity.user_id == self.user_id,
                CompanyStateEntity.entity_type == event.payload.get("entity_type"),
                CompanyStateEntity.is_active.is_(True),
            )
        )
        for ent in result.scalars():
            if " ".join(ent.title.split()).casefold() == title_norm:
                return ent
        return None

    async def _gate(self, event: ObservedEvent) -> float | None:
        """Returns confidence for acceptance, or None for rejection."""
        p = event.payload
        candidate = write_gate.EntityCandidate(
            entity_type=p.get("entity_type", "note"),
            title=str(p.get("title", "")),
            # B1: gate on the full body, not the truncated summary
            body=str(p.get("body") or p.get("summary") or ""),
            frontmatter_keys=tuple((p.get("attributes") or {}).get("frontmatter", {}).keys()),
            tags=tuple((p.get("attributes") or {}).get("tags", ())),
            has_headings=bool(p.get("has_headings", False)),
        )
        decision, _reasons = write_gate.evaluate(candidate)
        if decision is write_gate.GateDecision.REJECT:
            return None
        if decision is write_gate.GateDecision.ACCEPT:
            return 0.700
        # BORDERLINE → bounded judge; budget-exhausted/timeout/error → fail-open 0.5
        if self.counters.judge_calls >= self.judge_max_calls:
            return write_gate.FAIL_OPEN_CONFIDENCE
        self.counters.judge_calls += 1
        if self._provider is None:
            self._provider = self.provider_factory()
        keep, reason, fail_open = await write_gate.judge(
            candidate, self._provider, self.judge_timeout_s,
        )
        if not keep:
            logger.info("write-gate judge rejected %s: %s", event.external_id, reason)
            return None
        # Structured flag, not reason-string sniffing (review nit): only a real
        # judge failure downgrades confidence.
        return write_gate.FAIL_OPEN_CONFIDENCE if fail_open else 0.700

    async def _dedup_or_create(self, event, observation, confidence: float):
        p = event.payload
        cand = _as_candidate(event)
        vec = (await self.embedder.embed_batch([dedup_mod.embed_text_for(cand)]))[0]
        match_id, _sim = await dedup_mod.find_similar(
            self.db, self.user_id, p.get("entity_type"), vec, self.sim_threshold,
        )
        if match_id:
            entity = await self.db.get(CompanyStateEntity, match_id)
            changes = dedup_mod.merge(entity, cand, observation)
            await self._apply_changes(entity, changes, vec_if_reembed=vec)
            self.counters.merged += 1
            return entity, "merged"

        entity = CompanyStateEntity(
            user_id=self.user_id,
            entity_type=p.get("entity_type", "note"),
            title=str(p.get("title", ""))[:5000],
            status=p.get("status") or ("open" if p.get("entity_type") == "task" else "active"),
            summary=p.get("summary"),
            attributes=p.get("attributes") or {},
            source=event.provenance,
            source_id=self.source_id,
            external_ref=event.external_id,
            confidence=confidence,
            last_asserted_at=event.observed_at,
            embedding=vec,
        )
        self.db.add(entity)
        await self.db.flush()
        self.counters.created += 1
        return entity, "created"

    async def _apply_changes(self, entity: CompanyStateEntity, changes: dict, vec_if_reembed=None) -> None:
        reembed = changes.pop("_reembed", False)
        for key, value in changes.items():
            setattr(entity, key, value)
        if reembed:
            if vec_if_reembed is not None:
                entity.embedding = vec_if_reembed
            else:
                cand_text = f"{entity.entity_type}: {entity.title}\n{(entity.summary or '')[:500]}"
                entity.embedding = (await self.embedder.embed_batch([cand_text]))[0]
        await self.db.flush()

    async def _upsert_relations(self, event: ObservedEvent, entity: CompanyStateEntity) -> None:
        hints = event.payload.get("relation_hints") or {}
        edges: list[tuple[uuid.UUID, uuid.UUID, str]] = []

        derived = await self._resolve_hint(hints.get("derived_from_note"))
        if derived:
            edges.append((entity.id, derived, "derived_from"))
        parent = await self._resolve_hint(hints.get("parent_task_external_id"))
        if parent:
            edges.append((entity.id, parent, "part_of"))

        proj_name = hints.get("part_of_project")
        if proj_name:
            proj_id = await self._find_by_title("project", proj_name)
            if proj_id:
                edges.append((entity.id, proj_id, "part_of"))
        for mention in hints.get("mentions") or []:
            for etype in ("goal", "project"):
                target = await self._find_by_title(etype, str(mention))
                if target and target != entity.id:
                    edges.append((entity.id, target, "mentions"))

        for src, tgt, rtype in edges:
            await self.db.execute(
                text("""
                    INSERT INTO state_relations
                        (user_id, source_entity_id, target_entity_id, relation_type)
                    VALUES (:u, :s, :t, :r)
                    ON CONFLICT (source_entity_id, target_entity_id, relation_type)
                    DO NOTHING
                """),
                {"u": str(self.user_id), "s": str(src), "t": str(tgt), "r": rtype},
            )

    async def _resolve_hint(self, external_id: str | None) -> uuid.UUID | None:
        """Resolve a relation-hint external_id to an entity id.

        In-run map first; fall back to the observation trail (S1) so hints
        still resolve when the target's event was `unchanged` this run (e.g. a
        checkbox added to an otherwise-unmodified note).
        """
        if not external_id:
            return None
        if external_id in self._run_entities:
            return self._run_entities[external_id]
        row = (await self.db.execute(
            text("""
                SELECT entity_id FROM state_observations
                WHERE source_id = :sid AND external_id = :eid AND entity_id IS NOT NULL
                ORDER BY observed_at DESC LIMIT 1
            """),
            {"sid": str(self.source_id), "eid": external_id},
        )).fetchone()
        return row.entity_id if row else None

    async def _find_by_title(self, entity_type: str, title: str) -> uuid.UUID | None:
        norm = " ".join(title.split()).casefold()
        result = await self.db.execute(
            select(CompanyStateEntity.id, CompanyStateEntity.title).where(
                CompanyStateEntity.user_id == self.user_id,
                CompanyStateEntity.entity_type == entity_type,
                CompanyStateEntity.is_active.is_(True),
            )
        )
        for row in result:
            if " ".join(row.title.split()).casefold() == norm:
                return row.id
        return None

    async def _finish_observation(self, observation_row, outcome: str, entity_id) -> None:
        await self.db.execute(
            text("""
                UPDATE state_observations
                SET processed_at = NOW(), outcome = :o, entity_id = :e
                WHERE id = :id
            """),
            {"o": outcome, "e": str(entity_id) if entity_id else None,
             "id": str(observation_row.id)},
        )


def _as_candidate(event: ObservedEvent):
    """Shape the event payload like an entity for dedup/merge (duck-typed)."""
    from types import SimpleNamespace

    p = event.payload
    return SimpleNamespace(
        entity_type=p.get("entity_type", "note"),
        title=str(p.get("title", "")),
        summary=p.get("summary"),
        status=p.get("status"),
        attributes=p.get("attributes") or {},
    )
