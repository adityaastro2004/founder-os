"""Company State Engine API (arch §5). All endpoints require_auth + user-scoped.

No entity/relation write endpoints in slice 1 — the reconciler is the only
writer (arch §10 guardrail). Scoped lookups return 404, never 403 (no leaks).
"""
from __future__ import annotations

import logging
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ClerkUser, require_auth
from app.database import get_db
from app.redis import get_redis
from app.state.models import CompanyStateEntity, StateObservation, StateRelation, StateSource
from app.users import get_or_create_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/state", tags=["state"])


# ── Request / Response models ────────────────────────────────────────────

class ObsidianConfig(BaseModel):
    vault_path: str = Field(..., min_length=1, max_length=1024)
    managed_folder: str = Field("FounderOS", min_length=1, max_length=255, pattern=r"^[A-Za-z0-9 _-]+$")
    exclude_dirs: Optional[list[str]] = None


class SourceCreateRequest(BaseModel):
    type: Literal["obsidian"]
    name: Optional[str] = Field(None, max_length=255)
    config: ObsidianConfig


class SourceUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    config: Optional[ObsidianConfig] = None
    status: Optional[Literal["active", "paused"]] = None


class HealthOut(BaseModel):
    ok: bool
    detail: str = ""


class SourceResponse(BaseModel):
    id: uuid.UUID
    type: str
    name: str
    config: dict
    status: str
    last_synced_at: Optional[str] = None
    last_error: Optional[str] = None
    last_sync_report: Optional[dict] = None
    health: Optional[HealthOut] = None


class SourceListResponse(BaseModel):
    sources: list[SourceResponse]
    total: int


class SyncTriggerRequest(BaseModel):
    direction: Literal["both", "inbound", "outbound"] = "both"


class SyncSubmittedResponse(BaseModel):
    task_id: str
    status: str = "queued"
    poll: str


class EntitySummary(BaseModel):
    """The provenance contract (US-4)."""
    id: uuid.UUID
    entity_type: str
    title: str
    status: str
    summary: Optional[str] = None
    source: str
    source_id: Optional[uuid.UUID] = None
    source_name: Optional[str] = None
    external_ref: Optional[str] = None
    confidence: float
    last_asserted_at: str
    pinned: bool
    created_at: str
    updated_at: str


class EntityListResponse(BaseModel):
    entities: list[EntitySummary]
    total: int
    limit: int
    offset: int


class RelationOut(BaseModel):
    id: uuid.UUID
    source_entity_id: uuid.UUID
    target_entity_id: uuid.UUID
    relation_type: str
    strength: float


class ObservationOut(BaseModel):
    kind: str
    observed_at: str
    outcome: Optional[str] = None
    content_hash: str


class EntityDetail(EntitySummary):
    attributes: dict
    relations_out: list[RelationOut]
    relations_in: list[RelationOut]
    recent_observations: list[ObservationOut]


class RelationListResponse(BaseModel):
    relations: list[RelationOut]
    total: int


# ── Helpers ──────────────────────────────────────────────────────────────

async def _uid(user: ClerkUser, db: AsyncSession) -> uuid.UUID:
    return await get_or_create_user_id(user.user_id, db, email=user.email)


def _validated_config(config: ObsidianConfig) -> dict:
    from app.integrations.obsidian.client import validate_vault_path

    try:
        resolved = validate_vault_path(config.vault_path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"vault_path: {exc}")
    excludes = config.exclude_dirs or [".obsidian", ".trash", "Templates"]
    if config.managed_folder not in excludes:
        excludes = [*excludes, config.managed_folder]
    return {
        "vault_path": str(resolved),
        "managed_folder": config.managed_folder,
        "exclude_dirs": excludes,
    }


async def _get_source_scoped(source_id: uuid.UUID, uid: uuid.UUID, db: AsyncSession) -> StateSource:
    source = (await db.execute(
        select(StateSource).where(StateSource.id == source_id, StateSource.user_id == uid)
    )).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


def _source_out(source: StateSource, health: HealthOut | None = None) -> SourceResponse:
    return SourceResponse(
        id=source.id, type=source.type, name=source.name, config=source.config,
        status=source.status,
        last_synced_at=source.last_synced_at.isoformat() if source.last_synced_at else None,
        last_error=source.last_error, last_sync_report=source.last_sync_report,
        health=health,
    )


def _entity_out(e: CompanyStateEntity, source_name: str | None = None) -> EntitySummary:
    return EntitySummary(
        id=e.id, entity_type=e.entity_type, title=e.title, status=e.status,
        summary=e.summary, source=e.source, source_id=e.source_id,
        source_name=source_name, external_ref=e.external_ref,
        confidence=float(e.confidence),
        last_asserted_at=e.last_asserted_at.isoformat(),
        pinned=e.pinned, created_at=e.created_at.isoformat(),
        updated_at=e.updated_at.isoformat(),
    )


def _rel_out(r: StateRelation) -> RelationOut:
    return RelationOut(
        id=r.id, source_entity_id=r.source_entity_id, target_entity_id=r.target_entity_id,
        relation_type=r.relation_type, strength=float(r.strength),
    )


# ── Sources ──────────────────────────────────────────────────────────────

@router.post("/sources", response_model=SourceResponse, status_code=201)
async def create_source(
    body: SourceCreateRequest,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    uid = await _uid(user, db)
    config = _validated_config(body.config)
    name = body.name or config["vault_path"].rstrip("/").rsplit("/", 1)[-1]

    dupe = (await db.execute(
        select(StateSource).where(
            StateSource.user_id == uid, StateSource.type == body.type, StateSource.name == name,
        )
    )).scalar_one_or_none()
    if dupe:
        raise HTTPException(status_code=409, detail=f"Source '{name}' already registered")

    source = StateSource(user_id=uid, type=body.type, name=name, config=config)
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return _source_out(source)


@router.get("/sources", response_model=SourceListResponse)
async def list_sources(
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    from app.integrations.obsidian.adapter import ObsidianAdapter

    uid = await _uid(user, db)
    sources = list((await db.execute(
        select(StateSource).where(StateSource.user_id == uid).order_by(StateSource.created_at)
    )).scalars())
    adapter = ObsidianAdapter()
    out = []
    for s in sources:
        health = None
        if s.type == "obsidian":
            h = adapter.check_source(s.config)
            health = HealthOut(ok=h.ok, detail=h.detail)
        out.append(_source_out(s, health))
    return SourceListResponse(sources=out, total=len(out))


@router.get("/sources/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: uuid.UUID,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    uid = await _uid(user, db)
    return _source_out(await _get_source_scoped(source_id, uid, db))


@router.patch("/sources/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: uuid.UUID,
    body: SourceUpdateRequest,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    uid = await _uid(user, db)
    source = await _get_source_scoped(source_id, uid, db)
    if body.name is not None:
        source.name = body.name
    if body.config is not None:
        source.config = _validated_config(body.config)
    if body.status is not None:
        source.status = body.status
    await db.commit()
    await db.refresh(source)
    return _source_out(source)


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(
    source_id: uuid.UUID,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    uid = await _uid(user, db)
    source = await _get_source_scoped(source_id, uid, db)
    await db.delete(source)  # observations cascade; entities keep provenance (source_id NULL)
    await db.commit()


# ── Sync trigger (arch §8: always queued) ────────────────────────────────

@router.post("/sources/{source_id}/sync", response_model=SyncSubmittedResponse, status_code=202)
async def trigger_sync(
    source_id: uuid.UUID,
    body: SyncTriggerRequest,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    from app.tasks.state_tasks import state_sync_task, sync_lock_key, LOCK_TTL_S

    uid = await _uid(user, db)
    source = await _get_source_scoped(source_id, uid, db)
    if source.status == "paused":
        raise HTTPException(status_code=409, detail="Source is paused")

    redis = get_redis()
    # NX guard here gives an immediate 409; the task re-takes/holds the same key.
    got = await redis.set(sync_lock_key(str(source_id)), "queued", nx=True, ex=LOCK_TTL_S)
    if not got:
        raise HTTPException(status_code=409, detail="A sync is already running for this source")

    result = state_sync_task.delay(str(source_id), str(uid), body.direction)
    return SyncSubmittedResponse(task_id=result.id, poll=f"/api/state/sources/{source_id}")


# ── Entities (read-only; provenance = US-4) ──────────────────────────────

@router.get("/entities", response_model=EntityListResponse)
async def list_entities(
    entity_type: Optional[str] = Query(None, max_length=50),
    status: Optional[str] = Query(None, max_length=50),
    q: Optional[str] = Query(None, max_length=200),
    include_archived: bool = False,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    uid = await _uid(user, db)
    conds = [CompanyStateEntity.user_id == uid]
    if not include_archived:
        conds.append(CompanyStateEntity.is_active.is_(True))
    if entity_type:
        conds.append(CompanyStateEntity.entity_type == entity_type)
    if status:
        conds.append(CompanyStateEntity.status == status)
    if q:
        conds.append(CompanyStateEntity.title.ilike(f"%{q}%"))

    total = (await db.execute(
        select(func.count()).select_from(CompanyStateEntity).where(*conds)
    )).scalar_one()
    rows = (await db.execute(
        select(CompanyStateEntity, StateSource.name)
        .outerjoin(StateSource, CompanyStateEntity.source_id == StateSource.id)
        .where(*conds)
        .order_by(CompanyStateEntity.last_asserted_at.desc())
        .limit(limit).offset(offset)
    )).all()
    return EntityListResponse(
        entities=[_entity_out(e, name) for e, name in rows],
        total=total, limit=limit, offset=offset,
    )


@router.get("/entities/{entity_id}", response_model=EntityDetail)
async def get_entity(
    entity_id: uuid.UUID,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    uid = await _uid(user, db)
    row = (await db.execute(
        select(CompanyStateEntity, StateSource.name)
        .outerjoin(StateSource, CompanyStateEntity.source_id == StateSource.id)
        .where(CompanyStateEntity.id == entity_id, CompanyStateEntity.user_id == uid)
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    entity, source_name = row

    # user_id predicate is redundant with the scoped anchor entity, but makes
    # the no-cross-user-leak invariant local instead of inferred (security N2).
    rels_out = list((await db.execute(
        select(StateRelation).where(
            StateRelation.source_entity_id == entity.id, StateRelation.user_id == uid,
        )
    )).scalars())
    rels_in = list((await db.execute(
        select(StateRelation).where(
            StateRelation.target_entity_id == entity.id, StateRelation.user_id == uid,
        )
    )).scalars())
    observations = list((await db.execute(
        select(StateObservation)
        .where(StateObservation.entity_id == entity.id, StateObservation.user_id == uid)
        .order_by(StateObservation.observed_at.desc()).limit(5)
    )).scalars())

    base = _entity_out(entity, source_name)
    return EntityDetail(
        **base.model_dump(),
        attributes=entity.attributes,
        relations_out=[_rel_out(r) for r in rels_out],
        relations_in=[_rel_out(r) for r in rels_in],
        recent_observations=[
            ObservationOut(
                kind=o.kind, observed_at=o.observed_at.isoformat(),
                outcome=o.outcome, content_hash=o.content_hash,
            ) for o in observations
        ],
    )


@router.get("/relations", response_model=RelationListResponse)
async def list_relations(
    entity_id: Optional[uuid.UUID] = None,
    relation_type: Optional[str] = Query(None, max_length=50),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    uid = await _uid(user, db)
    conds = [StateRelation.user_id == uid]
    if entity_id:
        conds.append(or_(
            StateRelation.source_entity_id == entity_id,
            StateRelation.target_entity_id == entity_id,
        ))
    if relation_type:
        conds.append(StateRelation.relation_type == relation_type)

    total = (await db.execute(
        select(func.count()).select_from(StateRelation).where(*conds)
    )).scalar_one()
    rows = list((await db.execute(
        select(StateRelation).where(*conds)
        .order_by(StateRelation.created_at.desc()).limit(limit).offset(offset)
    )).scalars())
    return RelationListResponse(relations=[_rel_out(r) for r in rows], total=total)
