"""Company State Engine API (arch §5). All endpoints require_auth + user-scoped.

No entity/relation write endpoints in slice 1 — the reconciler is the only
writer (arch §10 guardrail). Scoped lookups return 404, never 403 (no leaks).
"""
from __future__ import annotations

import logging
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ClerkUser, require_auth
from app.config import get_settings
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


class NotionConfig(BaseModel):
    managed_root_page_id: str = Field(..., min_length=32, max_length=36)
    # Token travels in the REQUEST BODY ONLY (SecretStr: repr shows '******');
    # it is popped and upserted into the integrations table — NEVER persisted
    # in state_sources.config (arch §2.1).
    token: Optional[SecretStr] = None
    database_map: Optional[dict[str, Literal["task", "goal", "project", "decision", "note"]]] = None
    exclude_page_ids: Optional[list[str]] = None


class SourceCreateRequest(BaseModel):
    type: Literal["obsidian", "notion"]
    name: Optional[str] = Field(None, max_length=255)
    config: ObsidianConfig | NotionConfig


class SourceUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    config: Optional[ObsidianConfig | NotionConfig] = None
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
    full_walk: bool = False  # D6: operator escape hatch; forces archival diff (arch §6)


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


async def _validated_config(config: ObsidianConfig) -> dict:
    from anyio import to_thread

    from app.integrations.obsidian.client import validate_vault_path

    try:
        # stat/access are blocking filesystem calls — off the event loop (S3)
        resolved = await to_thread.run_sync(validate_vault_path, config.vault_path)
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


async def _upsert_notion_token(db: AsyncSession, uid: uuid.UUID, token: str) -> None:
    from app.models import Integration

    row = (await db.execute(
        select(Integration).where(
            Integration.user_id == uid, Integration.integration_type == "notion",
        )
    )).scalar_one_or_none()
    if row:
        row.access_token = token
        row.is_active = True
    else:
        db.add(Integration(user_id=uid, integration_type="notion",
                           display_name="Notion", access_token=token, is_active=True))
    await db.flush()


async def _validated_notion_config(
    config: NotionConfig, uid: uuid.UUID, db: AsyncSession, *, token_required: bool,
) -> dict:
    """Pop the token → integrations upsert → ONE live validation call (arch §2.1).
    The returned config dict NEVER contains the token."""
    from app.integrations.credentials import CredentialsMissing, resolve_source_credentials
    from app.integrations.notion import mapper
    from app.integrations.notion.client import NotionAPIError, NotionAuthError, NotionClient

    root_id = mapper.normalize_uuid(config.managed_root_page_id)
    if len(root_id) != 36:
        raise HTTPException(status_code=422, detail="managed_root_page_id is not a Notion page id")

    token = config.token.get_secret_value() if config.token else None
    if token:
        await _upsert_notion_token(db, uid, token)
    else:
        class _Src:  # minimal shape for the resolver
            type = "notion"
            user_id = uid
        try:
            token = (await resolve_source_credentials(db, _Src()))["token"]
        except CredentialsMissing:
            if token_required:
                raise HTTPException(status_code=422, detail="config.token is required — no active Notion integration for this user")
            token = None

    if token:
        settings = get_settings()
        client = NotionClient(token, api_version=settings.STATE_NOTION_API_VERSION,
                              timeout_s=10)
        try:
            page = await client.get_page(root_id)
            if page.get("archived") or page.get("in_trash"):
                raise HTTPException(status_code=422, detail="managed root page is archived/trashed")
        except NotionAuthError:
            raise HTTPException(status_code=422, detail="Notion token invalid")
        except NotionAPIError as exc:
            if exc.status == 404:
                raise HTTPException(status_code=422, detail="managed root page not shared with the integration")
            raise HTTPException(status_code=422, detail=f"Notion validation failed (HTTP {exc.status})")
        finally:
            await client.close()

    out: dict = {"managed_root_page_id": root_id}
    if config.database_map:
        out["database_map"] = {mapper.normalize_uuid(k): v for k, v in config.database_map.items()}
    if config.exclude_page_ids:
        out["exclude_page_ids"] = [mapper.normalize_uuid(x) for x in config.exclude_page_ids]
    return out


async def _config_for(body_config, body_type: str, uid: uuid.UUID, db: AsyncSession,
                      *, token_required: bool) -> dict:
    if body_type == "notion":
        if not isinstance(body_config, NotionConfig):
            raise HTTPException(status_code=422, detail="config shape does not match type=notion")
        return await _validated_notion_config(body_config, uid, db, token_required=token_required)
    if not isinstance(body_config, ObsidianConfig):
        raise HTTPException(status_code=422, detail="config shape does not match type=obsidian")
    return await _validated_config(body_config)


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
    config = await _config_for(body.config, body.type, uid, db, token_required=True)
    if body.type == "obsidian":
        default_name = config["vault_path"].rstrip("/").rsplit("/", 1)[-1]
    else:
        default_name = f"notion-{config['managed_root_page_id'][:8]}"
    name = body.name or default_name

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
    from anyio import to_thread

    from app.integrations import registry

    uid = await _uid(user, db)
    sources = list((await db.execute(
        select(StateSource).where(StateSource.user_id == uid).order_by(StateSource.created_at)
    )).scalars())
    out = []
    has_notion_token = None
    for s in sources:
        health = None
        if s.type == "obsidian":
            adapter = registry.get("obsidian")  # ADR-010: registry lookup
            # capped vault walk = blocking IO — off the event loop (S3)
            h = await to_thread.run_sync(adapter.check_source, s.config)
            health = HealthOut(ok=h.ok, detail=h.detail)
        elif s.type == "notion":
            if has_notion_token is None:
                from app.integrations.credentials import (
                    CredentialsMissing, resolve_source_credentials,
                )
                try:
                    await resolve_source_credentials(db, s)
                    has_notion_token = True
                except CredentialsMissing:
                    has_notion_token = False
            adapter = registry.get("notion")
            h = adapter.check_source(s.config, has_token=has_notion_token)  # non-network (§8.2)
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
        source.config = await _config_for(body.config, source.type, uid, db,
                                          token_required=False)
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
    # NX guard here gives an immediate 409; the task takes over and releases it.
    key = sync_lock_key(str(source_id))
    got = await redis.set(key, "queued", nx=True, ex=LOCK_TTL_S)
    if not got:
        raise HTTPException(status_code=409, detail="A sync is already running for this source")

    try:
        result = state_sync_task.delay(str(source_id), str(uid), body.direction,
                                       body.full_walk)
    except Exception as exc:
        # Broker down: release the reservation instead of 900s of false 409s.
        await redis.delete(key)
        logger.error("sync enqueue failed for %s: %s", source_id, exc)
        raise HTTPException(status_code=503, detail="Task queue unavailable — try again")
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
