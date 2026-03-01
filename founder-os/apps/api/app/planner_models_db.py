"""
Founder OS — Planner & Memory ORM Models
============================================
SQLAlchemy models for:
  - PlannerUser   — persistent user profiles + Google Calendar tokens
  - PlanHistory   — historical plan records
  - MemoryPage    — temporal knowledge graph pages
  - MemoryLink    — explicit relationships between memories
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _ts_now() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


def _ts_now_nullable() -> Mapped[Optional[datetime]]:
    return mapped_column(DateTime(timezone=True), nullable=True)


# ============================================================================
# PLANNER USERS
# ============================================================================

class PlannerUser(Base):
    __tablename__ = "planner_users"

    user_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), default="", server_default="")

    # Business context
    business_name: Mapped[str] = mapped_column(String(255), default="", server_default="")
    business_type: Mapped[str] = mapped_column(String(100), default="", server_default="")
    business_stage: Mapped[str] = mapped_column(String(100), default="", server_default="")
    industry: Mapped[str] = mapped_column(String(100), default="", server_default="")
    target_audience: Mapped[str] = mapped_column(Text, default="", server_default="")
    team_size: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    # Metrics
    current_mrr: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, server_default="0")
    current_users: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    mrr_growth_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, server_default="0")

    # Weekly planning
    primary_goal: Mapped[str] = mapped_column(Text, default="", server_default="")
    goals_this_week: Mapped[Optional[list]] = mapped_column(JSONB, server_default="[]")
    completed_last_week: Mapped[Optional[list]] = mapped_column(JSONB, server_default="[]")
    blockers: Mapped[Optional[list]] = mapped_column(JSONB, server_default="[]")
    custom_instructions: Mapped[str] = mapped_column(Text, default="", server_default="")

    # Preferences
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Kolkata", server_default="Asia/Kolkata")
    preferred_work_hours: Mapped[str] = mapped_column(String(20), default="09:00-18:00", server_default="09:00-18:00")
    calendar_id: Mapped[str] = mapped_column(String(255), default="primary", server_default="primary")

    # Google Calendar OAuth tokens
    gcal_connected: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    gcal_access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gcal_refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gcal_token_expiry: Mapped[Optional[datetime]] = _ts_now_nullable()
    gcal_token_data: Mapped[Optional[dict]] = mapped_column(JSONB, server_default="{}")

    # Stats
    plan_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_plan_at: Mapped[Optional[datetime]] = _ts_now_nullable()
    last_plan_events: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Timestamps
    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = _ts_now()

    # Relationships
    plan_records: Mapped[list["PlanHistory"]] = relationship(
        back_populates="user", cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<PlannerUser {self.user_id}: {self.business_name}>"


# ============================================================================
# PLAN HISTORY
# ============================================================================

class PlanHistory(Base):
    __tablename__ = "plan_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    user_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("planner_users.user_id", ondelete="CASCADE"), nullable=False,
    )

    plan_id: Mapped[Optional[str]] = mapped_column(String(50))
    week_of: Mapped[Optional[Any]] = mapped_column(Date)
    generated_at: Mapped[datetime] = _ts_now()

    task_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    events_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    events_failed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    duration_seconds: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 1))

    top_priorities: Mapped[Optional[list]] = mapped_column(JSONB, server_default="[]")
    plan_data: Mapped[Optional[dict]] = mapped_column(JSONB, server_default="{}")
    gcal_events: Mapped[Optional[list]] = mapped_column(JSONB, server_default="[]")

    created_at: Mapped[datetime] = _ts_now()

    user: Mapped["PlannerUser"] = relationship(back_populates="plan_records")

    def __repr__(self) -> str:
        return f"<PlanHistory {self.plan_id} for {self.user_id}>"


# ============================================================================
# MEMORY PAGES — Temporal Knowledge Graph
# ============================================================================

class MemoryPage(Base):
    """
    A discrete memory unit in the temporal knowledge graph.

    Each page represents something the system should remember about a user's
    business: events, decisions, milestones, metrics, insights, etc.

    Retrieval uses composite scoring:
      score = (semantic_sim × w1) + (temporal_relevance × w2) + (importance × w3) + (access_freq × w4)
    where temporal_relevance = importance × exp(-decay_rate × days_since_occurred)
    """
    __tablename__ = "memory_pages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    user_id: Mapped[str] = mapped_column(String(100), nullable=False)

    # Classification
    page_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="event", server_default="event",
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Temporal metadata
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = _ts_now()
    last_accessed_at: Mapped[datetime] = _ts_now()
    access_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Importance & Decay
    importance: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("0.500"), server_default="0.500")
    decay_rate: Mapped[Decimal] = mapped_column(Numeric(6, 5), default=Decimal("0.00100"), server_default="0.00100")
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # Review scheduling
    next_review_at: Mapped[Optional[datetime]] = _ts_now_nullable()
    review_interval_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    review_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_reviewed_at: Mapped[Optional[datetime]] = _ts_now_nullable()

    # Organisation
    chapter: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text), server_default="{}")
    entities: Mapped[Optional[dict]] = mapped_column(JSONB, server_default="{}")

    # Relations
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memory_pages.id", ondelete="SET NULL"), nullable=True,
    )
    related_ids: Mapped[Optional[list]] = mapped_column(ARRAY(UUID(as_uuid=True)), server_default="{}")

    # Embedding
    embedding = mapped_column(Vector(1536), nullable=True)

    # Source & metadata
    source: Mapped[str] = mapped_column(String(100), default="user_input", server_default="user_input")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata_", JSONB, server_default="{}")

    # Soft delete
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    # Relationships
    outgoing_links: Mapped[list["MemoryLink"]] = relationship(
        foreign_keys="MemoryLink.source_id",
        back_populates="source_page",
        cascade="all, delete-orphan",
    )
    incoming_links: Mapped[list["MemoryLink"]] = relationship(
        foreign_keys="MemoryLink.target_id",
        back_populates="target_page",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<MemoryPage '{self.title}' ({self.page_type})>"


# ============================================================================
# MEMORY LINKS — relationships between memories
# ============================================================================

class MemoryLink(Base):
    """
    Explicit typed relationship between two memory pages.

    Link types:
      - related    — general association
      - caused_by  — A was caused by B
      - led_to     — A led to B
      - contradicts — A contradicts B
      - updates    — A updates/supersedes B
      - supersedes — A fully replaces B
      - part_of    — A is a sub-memory of B
    """
    __tablename__ = "memory_links"
    __table_args__ = (
        UniqueConstraint("source_id", "target_id", "link_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memory_pages.id", ondelete="CASCADE"), nullable=False,
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memory_pages.id", ondelete="CASCADE"), nullable=False,
    )
    link_type: Mapped[str] = mapped_column(String(50), nullable=False, default="related", server_default="related")
    strength: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0.50"), server_default="0.50")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata_", JSONB, server_default="{}")
    created_at: Mapped[datetime] = _ts_now()

    source_page: Mapped["MemoryPage"] = relationship(
        foreign_keys=[source_id], back_populates="outgoing_links",
    )
    target_page: Mapped["MemoryPage"] = relationship(
        foreign_keys=[target_id], back_populates="incoming_links",
    )

    def __repr__(self) -> str:
        return f"<MemoryLink {self.source_id} --{self.link_type}--> {self.target_id}>"
