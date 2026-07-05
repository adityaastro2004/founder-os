"""Company State Engine (slice 1): state_sources, company_state_entities,
state_observations, state_relations.

Revision ID: 0002_state_engine
Revises: 0001_workflow_engine
Create Date: 2026-07-06

ADR-009 / arch doc 2026-07-04 §1.7. These four tables are genuinely new (not in
schema.sql), so plain creates in FK order — with the 0001 `_has_table` guard so
a partially-applied DB re-runs safely. Downgrade drops them (wholly owned here).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0002_state_engine"
down_revision = "0001_workflow_engine"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table("state_sources"):
        op.create_table(
            "state_sources",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("uuid_generate_v4()")),
            sa.Column("user_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("type", sa.String(50), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("config", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'")),
            sa.Column("sync_cursor", postgresql.JSONB, nullable=True),
            sa.Column("status", sa.String(50), nullable=False, server_default=sa.text("'active'")),
            sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text, nullable=True),
            sa.Column("last_sync_report", postgresql.JSONB, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("user_id", "type", "name"),
            sa.CheckConstraint(
                "type IN ('obsidian','github','stripe','slack','calendar','notion','user_doc','system')",
                name="ck_state_sources_type",
            ),
        )
        op.create_index("ix_state_sources_user", "state_sources", ["user_id"])

    if not _has_table("company_state_entities"):
        op.create_table(
            "company_state_entities",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("uuid_generate_v4()")),
            sa.Column("user_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("entity_type", sa.String(50), nullable=False),
            sa.Column("title", sa.Text, nullable=False),
            sa.Column("status", sa.String(50), nullable=False, server_default=sa.text("'active'")),
            sa.Column("summary", sa.Text, nullable=True),
            sa.Column("attributes", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'")),
            sa.Column("source", sa.String(20), nullable=False),
            sa.Column("source_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("state_sources.id", ondelete="SET NULL"), nullable=True),
            sa.Column("external_ref", sa.String(512), nullable=True),
            sa.Column("confidence", sa.Numeric(4, 3), nullable=False,
                      server_default=sa.text("'0.700'")),
            sa.Column("last_asserted_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("pinned", sa.Boolean, nullable=False, server_default=sa.text("false")),
            sa.Column("embedding", Vector(1536), nullable=True),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint(
                "entity_type IN ('goal','project','task','decision','metric','person','meeting','note')",
                name="ck_state_entities_type",
            ),
            sa.CheckConstraint(
                "source IN ('observed','user_doc','system')",
                name="ck_state_entities_source",
            ),
        )
        op.create_index("ix_state_entities_user_type", "company_state_entities",
                        ["user_id", "entity_type"])
        op.create_index(
            "uq_state_entities_user_src_ref", "company_state_entities",
            ["user_id", "source_id", "external_ref"], unique=True,
            postgresql_where=sa.text("external_ref IS NOT NULL"),
        )

    if not _has_table("state_observations"):
        op.create_table(
            "state_observations",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("uuid_generate_v4()")),
            sa.Column("source_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("state_sources.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("external_id", sa.String(512), nullable=False),
            sa.Column("kind", sa.String(100), nullable=False),
            sa.Column("payload", postgresql.JSONB, nullable=False),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column("provenance", sa.String(20), nullable=False,
                      server_default=sa.text("'observed'")),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("outcome", sa.String(50), nullable=True),
            sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("company_state_entities.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("source_id", "external_id", "content_hash",
                                name="uq_state_obs_dedup"),
            sa.CheckConstraint(
                "provenance IN ('observed','user_doc','system')",
                name="ck_state_obs_provenance",
            ),
        )
        op.create_index("ix_state_obs_lookup", "state_observations",
                        ["source_id", "external_id", "observed_at"])
        op.create_index("ix_state_obs_user", "state_observations", ["user_id"])

    if not _has_table("state_relations"):
        op.create_table(
            "state_relations",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("uuid_generate_v4()")),
            sa.Column("user_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("source_entity_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("company_state_entities.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("target_entity_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("company_state_entities.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("relation_type", sa.String(50), nullable=False,
                      server_default=sa.text("'mentions'")),
            sa.Column("strength", sa.Numeric(3, 2), nullable=False,
                      server_default=sa.text("'0.50'")),
            sa.Column("metadata_", postgresql.JSONB, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("source_entity_id", "target_entity_id", "relation_type"),
        )
        op.create_index("ix_state_relations_user", "state_relations", ["user_id"])


def downgrade() -> None:
    for table in ("state_relations", "state_observations", "company_state_entities",
                  "state_sources"):
        if _has_table(table):
            op.drop_table(table)
