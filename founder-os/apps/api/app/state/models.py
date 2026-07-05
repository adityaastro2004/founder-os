"""State Engine ORM (arch §1). Domain-scoped module on the shared Base —
mirrors the planner_models_db.py precedent; models.py deliberately not grown
(ADR-010 measurement note). Registered by import in app/main.py + alembic/env.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Feed values + entity types are CHECK-constrained NOW so the later feeds and
# the Curator land with zero schema change (spec §4 / arch §1.1).
PROVENANCE_FEEDS = ("observed", "user_doc", "system")
SOURCE_TYPES = ("obsidian", "github", "stripe", "slack", "calendar", "notion", "user_doc", "system")
ENTITY_TYPES = ("goal", "project", "task", "decision", "metric", "person", "meeting", "note")
RELATION_TYPES = ("part_of", "affects", "blocks", "mentions", "derived_from")


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )


def _ts_now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def _ts_nullable() -> Mapped[Optional[datetime]]:
    return mapped_column(DateTime(timezone=True), nullable=True)


class StateSource(Base):
    """A registered observation source per user (arch §1.2)."""

    __tablename__ = "state_sources"
    __table_args__ = (
        UniqueConstraint("user_id", "type", "name"),
        CheckConstraint(
            "type IN ('obsidian','github','stripe','slack','calendar','notion','user_doc','system')",
            name="ck_state_sources_type",
        ),
        Index("ix_state_sources_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    sync_cursor: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'active'"))
    last_synced_at: Mapped[Optional[datetime]] = _ts_nullable()
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_sync_report: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CompanyStateEntity(Base):
    """Typed canonical entity with provenance (arch §1.4)."""

    __tablename__ = "company_state_entities"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('goal','project','task','decision','metric','person','meeting','note')",
            name="ck_state_entities_type",
        ),
        CheckConstraint(
            "source IN ('observed','user_doc','system')",
            name="ck_state_entities_source",
        ),
        # Hard idempotency backstop: a re-sync can never double-create from the
        # same source block even if embedding dedup misbehaves.
        Index(
            "uq_state_entities_user_src_ref",
            "user_id",
            "source_id",
            "external_ref",
            unique=True,
            postgresql_where=text("external_ref IS NOT NULL"),
        ),
        Index("ix_state_entities_user_type", "user_id", "entity_type"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'active'"))
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("state_sources.id", ondelete="SET NULL"), nullable=True
    )
    external_ref: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    confidence: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False, server_default=text("'0.700'")
    )
    last_asserted_at: Mapped[datetime] = _ts_now()
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    embedding: Mapped[Optional[list]] = mapped_column(Vector(1536), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class StateObservation(Base):
    """Append-only inbound events — the Observe→Remember boundary (arch §1.3)."""

    __tablename__ = "state_observations"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", "content_hash", name="uq_state_obs_dedup"),
        CheckConstraint(
            "provenance IN ('observed','user_doc','system')",
            name="ck_state_obs_provenance",
        ),
        Index("ix_state_obs_lookup", "source_id", "external_id", "observed_at"),
        Index("ix_state_obs_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("state_sources.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    kind: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provenance: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'observed'")
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[Optional[datetime]] = _ts_nullable()
    outcome: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company_state_entities.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = _ts_now()


class StateRelation(Base):
    """Typed edge between entities — mirrors memory_links (arch §1.5)."""

    __tablename__ = "state_relations"
    __table_args__ = (
        UniqueConstraint("source_entity_id", "target_entity_id", "relation_type"),
        Index("ix_state_relations_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company_state_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company_state_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default=text("'mentions'")
    )
    strength: Mapped[float] = mapped_column(
        Numeric(3, 2), nullable=False, server_default=text("'0.50'")
    )
    metadata_: Mapped[dict] = mapped_column("metadata_", JSONB, server_default=text("'{}'"))
    created_at: Mapped[datetime] = _ts_now()
