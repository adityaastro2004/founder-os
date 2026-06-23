"""
Founder OS — SQLAlchemy ORM Models
Maps the full database schema to Python classes used by the API layer.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ============================================================================
# Helpers
# ============================================================================

def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )


def _ts_now() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


def _ts_now_nullable() -> Mapped[Optional[datetime]]:
    return mapped_column(DateTime(timezone=True), nullable=True)


# ============================================================================
# CORE — Users & Profiles
# ============================================================================

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    clerk_user_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    avatar_url: Mapped[Optional[str]] = mapped_column(Text)

    # Subscription
    subscription_tier: Mapped[str] = mapped_column(String(50), default="free", server_default="free")
    subscription_status: Mapped[str] = mapped_column(String(50), default="trial", server_default="trial")
    trial_ends_at: Mapped[Optional[datetime]] = _ts_now_nullable()
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(255))

    # Usage
    monthly_task_limit: Mapped[int] = mapped_column(Integer, default=100, server_default="100")
    monthly_tasks_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_reset_at: Mapped[datetime] = _ts_now()

    # Timestamps
    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = _ts_now()
    last_login_at: Mapped[Optional[datetime]] = _ts_now_nullable()
    deleted_at: Mapped[Optional[datetime]] = _ts_now_nullable()

    # Relationships
    profile: Mapped[Optional["FounderProfile"]] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    workflows: Mapped[list["Workflow"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    tasks: Mapped[list["Task"]] = relationship(back_populates="user", foreign_keys="Task.user_id", cascade="all, delete-orphan")
    knowledge_items: Mapped[list["KnowledgeItem"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    outputs: Mapped[list["Output"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    integrations: Mapped[list["Integration"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    agent_configs: Mapped[list["UserAgentConfig"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    notification_preferences: Mapped[Optional["NotificationPreference"]] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    usage_records: Mapped[list["UsageRecord"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User {self.email}>"


class FounderProfile(Base):
    __tablename__ = "founder_profiles"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    business_name: Mapped[Optional[str]] = mapped_column(String(255))
    business_type: Mapped[Optional[str]] = mapped_column(String(100))
    business_stage: Mapped[Optional[str]] = mapped_column(String(100))
    industry: Mapped[Optional[str]] = mapped_column(String(100))
    target_audience: Mapped[Optional[str]] = mapped_column(Text)

    primary_goal: Mapped[Optional[str]] = mapped_column(String(100))
    primary_goal_description: Mapped[Optional[str]] = mapped_column(Text)
    current_mrr: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    current_users: Mapped[Optional[int]] = mapped_column(Integer)
    monthly_traffic: Mapped[Optional[int]] = mapped_column(Integer)

    working_hours: Mapped[Optional[dict]] = mapped_column(JSONB)
    preferred_communication: Mapped[Optional[str]] = mapped_column(String(50))
    writing_voice: Mapped[Optional[str]] = mapped_column(Text)

    team_size: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    team_roles: Mapped[Optional[list]] = mapped_column(JSONB)

    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = _ts_now()

    user: Mapped["User"] = relationship(back_populates="profile")

    def __repr__(self) -> str:
        return f"<FounderProfile {self.business_name}>"


# ============================================================================
# AGENT SYSTEM
# ============================================================================

class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(100), default="claude-sonnet-4-20250514")
    temperature: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0.7"))
    max_tokens: Mapped[int] = mapped_column(Integer, default=4000)

    capabilities: Mapped[Optional[list]] = mapped_column(JSONB)
    available_tools: Mapped[Optional[list]] = mapped_column(JSONB)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    version: Mapped[str] = mapped_column(String(20), default="1.0", server_default="1.0")

    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = _ts_now()

    user_configs: Mapped[list["UserAgentConfig"]] = relationship(back_populates="agent", cascade="all, delete-orphan")
    tasks: Mapped[list["Task"]] = relationship(back_populates="agent")
    analytics: Mapped[list["AgentAnalytics"]] = relationship(back_populates="agent")
    learning_insights: Mapped[list["LearningInsight"]] = relationship(back_populates="agent")

    def __repr__(self) -> str:
        return f"<Agent {self.name}>"


class UserAgentConfig(Base):
    __tablename__ = "user_agent_configs"
    __table_args__ = (UniqueConstraint("user_id", "agent_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)

    custom_instructions: Mapped[Optional[str]] = mapped_column(Text)
    tone_adjustments: Mapped[Optional[str]] = mapped_column(Text)
    example_outputs: Mapped[Optional[list]] = mapped_column(JSONB)

    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    auto_execute: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = _ts_now()

    user: Mapped["User"] = relationship(back_populates="agent_configs")
    agent: Mapped["Agent"] = relationship(back_populates="user_configs")


# ============================================================================
# WORKFLOW SYSTEM
# ============================================================================

class WorkflowTemplate(Base):
    __tablename__ = "workflow_templates"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(String(100))

    steps: Mapped[list] = mapped_column(JSONB, nullable=False)

    trigger_type: Mapped[Optional[str]] = mapped_column(String(50))
    trigger_config: Mapped[Optional[dict]] = mapped_column(JSONB)
    estimated_duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)

    is_public: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    usage_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = _ts_now()

    workflows: Mapped[list["Workflow"]] = relationship(back_populates="template")

    def __repr__(self) -> str:
        return f"<WorkflowTemplate {self.slug}>"


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("workflow_templates.id"), nullable=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    steps: Mapped[list] = mapped_column(JSONB, nullable=False)

    is_scheduled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    schedule_cron: Mapped[Optional[str]] = mapped_column(String(100))
    next_run_at: Mapped[Optional[datetime]] = _ts_now_nullable()
    last_run_at: Mapped[Optional[datetime]] = _ts_now_nullable()

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    total_runs: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    successful_runs: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # n8n workflow identifier returned on push (ADR-008 / FR-2). NULL until compiled+pushed.
    n8n_workflow_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = _ts_now()

    user: Mapped["User"] = relationship(back_populates="workflows")
    template: Mapped[Optional["WorkflowTemplate"]] = relationship(back_populates="workflows")
    executions: Mapped[list["WorkflowExecution"]] = relationship(back_populates="workflow", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Workflow {self.name}>"


class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    status: Mapped[str] = mapped_column(String(50), default="pending", server_default="pending")
    trigger_type: Mapped[Optional[str]] = mapped_column(String(50))
    triggered_by: Mapped[Optional[dict]] = mapped_column(JSONB)

    current_step: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    total_steps: Mapped[int] = mapped_column(Integer, nullable=False)
    steps_completed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    steps_failed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    started_at: Mapped[Optional[datetime]] = _ts_now_nullable()
    completed_at: Mapped[Optional[datetime]] = _ts_now_nullable()
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)

    output_summary: Mapped[Optional[str]] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Per-step state sidecar (ADR-008 data-model delta). Keyed by IR step_id, e.g.
    # {"s1": {"status": "completed", "output": ...},
    #  "s2": {"status": "awaiting_approval", "approval_id": "...", "resume_url": "..."}}.
    # The authoritative home for per-step status / approval / n8n resume-URL and the
    # target of the C-1 atomic single-use transition. NULL until the first step runs.
    step_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = _ts_now()

    workflow: Mapped["Workflow"] = relationship(back_populates="executions")
    user: Mapped["User"] = relationship()
    tasks: Mapped[list["Task"]] = relationship(back_populates="workflow_execution", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<WorkflowExecution {self.id} status={self.status}>"


# ============================================================================
# TASK SYSTEM
# ============================================================================

class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = _uuid_pk()
    workflow_execution_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("workflow_executions.id", ondelete="CASCADE"), nullable=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"), nullable=False)

    task_type: Mapped[Optional[str]] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    input_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    output_data: Mapped[Optional[dict]] = mapped_column(JSONB)

    status: Mapped[str] = mapped_column(String(50), default="pending", server_default="pending")
    priority: Mapped[int] = mapped_column(Integer, default=5, server_default="5")

    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = _ts_now_nullable()
    approval_notes: Mapped[Optional[str]] = mapped_column(Text)

    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    started_at: Mapped[Optional[datetime]] = _ts_now_nullable()
    completed_at: Mapped[Optional[datetime]] = _ts_now_nullable()
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)

    tokens_used: Mapped[Optional[int]] = mapped_column(Integer)
    cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))

    error_message: Mapped[Optional[str]] = mapped_column(Text)
    error_details: Mapped[Optional[dict]] = mapped_column(JSONB)

    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = _ts_now()

    # Relationships
    user: Mapped["User"] = relationship(back_populates="tasks", foreign_keys=[user_id])
    approver: Mapped[Optional["User"]] = relationship(foreign_keys=[approved_by])
    agent: Mapped["Agent"] = relationship(back_populates="tasks")
    workflow_execution: Mapped[Optional["WorkflowExecution"]] = relationship(back_populates="tasks")
    outputs: Mapped[list["Output"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    context_usages: Mapped[list["ContextUsage"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    feedback: Mapped[list["TaskFeedback"]] = relationship(back_populates="task", cascade="all, delete-orphan")

    # Self-referencing via task_dependencies
    dependencies: Mapped[list["TaskDependency"]] = relationship(
        back_populates="task", foreign_keys="TaskDependency.task_id", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Task {self.title[:40]} status={self.status}>"


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (UniqueConstraint("task_id", "depends_on_task_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    depends_on_task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    dependency_type: Mapped[str] = mapped_column(String(50), default="blocking", server_default="blocking")
    created_at: Mapped[datetime] = _ts_now()

    task: Mapped["Task"] = relationship(foreign_keys=[task_id], back_populates="dependencies")
    depends_on: Mapped["Task"] = relationship(foreign_keys=[depends_on_task_id])


# ============================================================================
# CONTEXT & KNOWLEDGE
# ============================================================================

class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    title: Mapped[Optional[str]] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String(50))
    source_url: Mapped[Optional[str]] = mapped_column(Text)

    category: Mapped[Optional[str]] = mapped_column(String(100))
    tags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))

    embedding = mapped_column(Vector(1536), nullable=True)

    file_path: Mapped[Optional[str]] = mapped_column(Text)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))

    times_referenced: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_referenced_at: Mapped[Optional[datetime]] = _ts_now_nullable()

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    processing_status: Mapped[str] = mapped_column(String(50), default="pending", server_default="pending")

    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = _ts_now()

    user: Mapped["User"] = relationship(back_populates="knowledge_items")
    context_usages: Mapped[list["ContextUsage"]] = relationship(back_populates="knowledge_item", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<KnowledgeItem {self.title}>"


class ContextUsage(Base):
    __tablename__ = "context_usage"

    id: Mapped[uuid.UUID] = _uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    knowledge_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_items.id", ondelete="CASCADE"), nullable=False)
    relevance_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    was_useful: Mapped[Optional[bool]] = mapped_column(Boolean)
    created_at: Mapped[datetime] = _ts_now()

    task: Mapped["Task"] = relationship(back_populates="context_usages")
    knowledge_item: Mapped["KnowledgeItem"] = relationship(back_populates="context_usages")


class BusinessMetric(Base):
    __tablename__ = "business_metrics"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    metric_type: Mapped[Optional[str]] = mapped_column(String(100))
    metric_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    metric_unit: Mapped[Optional[str]] = mapped_column(String(50))
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    recorded_at: Mapped[datetime] = _ts_now()
    source: Mapped[Optional[str]] = mapped_column(String(100))
    source_id: Mapped[Optional[str]] = mapped_column(String(255))
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)

    created_at: Mapped[datetime] = _ts_now()

    user: Mapped["User"] = relationship()


# ============================================================================
# INTEGRATIONS
# ============================================================================

class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("user_id", "integration_type"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    integration_type: Mapped[Optional[str]] = mapped_column(String(100))
    display_name: Mapped[Optional[str]] = mapped_column(String(255))

    access_token: Mapped[Optional[str]] = mapped_column(Text)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text)
    token_expires_at: Mapped[Optional[datetime]] = _ts_now_nullable()

    config: Mapped[Optional[dict]] = mapped_column(JSONB)
    scopes: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    last_sync_at: Mapped[Optional[datetime]] = _ts_now_nullable()
    sync_status: Mapped[Optional[str]] = mapped_column(String(50))
    sync_error: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = _ts_now()

    user: Mapped["User"] = relationship(back_populates="integrations")
    syncs: Mapped[list["IntegrationSync"]] = relationship(back_populates="integration", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Integration {self.integration_type}>"


class IntegrationSync(Base):
    __tablename__ = "integration_syncs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    integration_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False)

    sync_type: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[Optional[str]] = mapped_column(String(50))
    records_synced: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    records_failed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = _ts_now_nullable()
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    details: Mapped[Optional[dict]] = mapped_column(JSONB)

    created_at: Mapped[datetime] = _ts_now()

    integration: Mapped["Integration"] = relationship(back_populates="syncs")


# ============================================================================
# OUTPUT MANAGEMENT
# ============================================================================

class Output(Base):
    __tablename__ = "outputs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    output_type: Mapped[Optional[str]] = mapped_column(String(100))
    title: Mapped[Optional[str]] = mapped_column(String(500))
    content: Mapped[Optional[str]] = mapped_column(Text)
    format: Mapped[Optional[str]] = mapped_column(String(50))

    word_count: Mapped[Optional[int]] = mapped_column(Integer)
    estimated_read_time_minutes: Mapped[Optional[int]] = mapped_column(Integer)

    publish_status: Mapped[str] = mapped_column(String(50), default="draft", server_default="draft")
    published_at: Mapped[Optional[datetime]] = _ts_now_nullable()
    published_to: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    external_urls: Mapped[Optional[dict]] = mapped_column(JSONB)

    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    parent_output_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("outputs.id"), nullable=True)

    user_rating: Mapped[Optional[int]] = mapped_column(Integer, CheckConstraint("user_rating >= 1 AND user_rating <= 5"))
    user_feedback: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = _ts_now()

    task: Mapped["Task"] = relationship(back_populates="outputs")
    user: Mapped["User"] = relationship(back_populates="outputs")
    parent: Mapped[Optional["Output"]] = relationship(remote_side="Output.id", backref="revisions")

    def __repr__(self) -> str:
        return f"<Output {self.title} v{self.version}>"


# ============================================================================
# ANALYTICS & LEARNING
# ============================================================================

class AgentAnalytics(Base):
    __tablename__ = "agent_analytics"
    __table_args__ = (UniqueConstraint("agent_id", "user_id", "metric_date"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"), nullable=False)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)

    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tasks_failed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    average_duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    average_tokens_used: Mapped[Optional[int]] = mapped_column(Integer)
    total_cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    approval_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    average_user_rating: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))

    created_at: Mapped[datetime] = _ts_now()

    agent: Mapped["Agent"] = relationship(back_populates="analytics")
    user: Mapped[Optional["User"]] = relationship()


class TaskFeedback(Base):
    __tablename__ = "task_feedback"

    id: Mapped[uuid.UUID] = _uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    rating: Mapped[Optional[int]] = mapped_column(Integer, CheckConstraint("rating >= 1 AND rating <= 5"))
    feedback_type: Mapped[Optional[str]] = mapped_column(String(50))
    comments: Mapped[Optional[str]] = mapped_column(Text)
    action_taken: Mapped[Optional[str]] = mapped_column(String(50))
    edits_made: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = _ts_now()

    task: Mapped["Task"] = relationship(back_populates="feedback")
    user: Mapped["User"] = relationship()


class LearningInsight(Base):
    __tablename__ = "learning_insights"

    id: Mapped[uuid.UUID] = _uuid_pk()
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"), nullable=False)

    insight_type: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)
    pattern_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    occurrences: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    improvement_action: Mapped[Optional[str]] = mapped_column(Text)
    applied_at: Mapped[Optional[datetime]] = _ts_now_nullable()

    created_at: Mapped[datetime] = _ts_now()

    agent: Mapped["Agent"] = relationship(back_populates="learning_insights")


# ============================================================================
# NOTIFICATIONS
# ============================================================================

class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    notification_type: Mapped[Optional[str]] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text)

    action_url: Mapped[Optional[str]] = mapped_column(Text)
    related_entity_type: Mapped[Optional[str]] = mapped_column(String(50))
    related_entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    read_at: Mapped[Optional[datetime]] = _ts_now_nullable()

    sent_via: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))

    created_at: Mapped[datetime] = _ts_now()

    user: Mapped["User"] = relationship(back_populates="notifications")


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("user_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    slack_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    preferences: Mapped[Optional[dict]] = mapped_column(JSONB, server_default=text("""'{
        "task_completed": true,
        "approval_needed": true,
        "workflow_failed": true,
        "weekly_summary": true,
        "tips_and_insights": false
    }'::jsonb"""))

    quiet_hours_start: Mapped[Optional[time]] = mapped_column(Time)
    quiet_hours_end: Mapped[Optional[time]] = mapped_column(Time)
    quiet_hours_timezone: Mapped[Optional[str]] = mapped_column(String(50))

    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = _ts_now()

    user: Mapped["User"] = relationship(back_populates="notification_preferences")


# ============================================================================
# BILLING & USAGE
# ============================================================================

class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)

    price_monthly_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    price_yearly_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))

    monthly_task_limit: Mapped[Optional[int]] = mapped_column(Integer)
    agent_limit: Mapped[Optional[int]] = mapped_column(Integer)
    workflow_limit: Mapped[Optional[int]] = mapped_column(Integer)
    knowledge_items_limit: Mapped[Optional[int]] = mapped_column(Integer)
    team_members_limit: Mapped[Optional[int]] = mapped_column(Integer)

    features: Mapped[Optional[list]] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = _ts_now()

    def __repr__(self) -> str:
        return f"<SubscriptionPlan {self.name}>"


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    usage_type: Mapped[Optional[str]] = mapped_column(String(100))
    quantity: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)

    recorded_at: Mapped[datetime] = _ts_now()
    billing_period_start: Mapped[Optional[date]] = mapped_column(Date)
    billing_period_end: Mapped[Optional[date]] = mapped_column(Date)

    user: Mapped["User"] = relationship(back_populates="usage_records")


# ============================================================================
# AUDIT & SECURITY
# ============================================================================

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(100))
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))

    changes: Mapped[Optional[dict]] = mapped_column(JSONB)
    ip_address = mapped_column(INET, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text)

    success: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = _ts_now()

    user: Mapped[Optional["User"]] = relationship()


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    name: Mapped[Optional[str]] = mapped_column(String(255))
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    key_prefix: Mapped[Optional[str]] = mapped_column(String(20))

    scopes: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))

    last_used_at: Mapped[Optional[datetime]] = _ts_now_nullable()
    usage_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    expires_at: Mapped[Optional[datetime]] = _ts_now_nullable()

    created_at: Mapped[datetime] = _ts_now()
    revoked_at: Mapped[Optional[datetime]] = _ts_now_nullable()

    user: Mapped["User"] = relationship(back_populates="api_keys")

    def __repr__(self) -> str:
        return f"<ApiKey {self.key_prefix}...>"


# ============================================================================
# AGENT RUNS & CHAT PERSISTENCE
# ============================================================================

class AgentRun(Base):
    """Persistent record of every agent interaction — input, output, metadata."""
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    agent_response: Mapped[str] = mapped_column(Text, nullable=False)

    model: Mapped[Optional[str]] = mapped_column(String(100))
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    duration_seconds: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    stop_reason: Mapped[Optional[str]] = mapped_column(String(50))

    tool_names: Mapped[Optional[list]] = mapped_column(JSONB)
    tool_calls_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # For orchestrator runs
    agents_used: Mapped[Optional[list]] = mapped_column(JSONB)
    delegations_made: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    delegation_details: Mapped[Optional[list]] = mapped_column(JSONB)

    status: Mapped[str] = mapped_column(String(50), default="completed", server_default="'completed'")

    created_at: Mapped[datetime] = _ts_now()

    def __repr__(self) -> str:
        return f"<AgentRun {self.agent_name} {self.created_at}>"


class ChatMessage(Base):
    """Persistent chat messages for agent and orchestrator chats."""
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Metadata for assistant messages
    model: Mapped[Optional[str]] = mapped_column(String(100))
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer)
    duration_seconds: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    tool_names: Mapped[Optional[list]] = mapped_column(JSONB)
    agents_used: Mapped[Optional[list]] = mapped_column(JSONB)
    delegations_made: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(50), default="completed", server_default="'completed'")

    created_at: Mapped[datetime] = _ts_now()

    def __repr__(self) -> str:
        return f"<ChatMessage {self.role} {self.agent_name} {self.created_at}>"


# ============================================================================
# USER INTELLIGENCE & BUSINESS INSIGHTS
# ============================================================================

class UserProfileIntel(Base):
    """Deep intelligence profile built from all agent interactions."""
    __tablename__ = "user_profiles_intel"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_profiles_intel_user"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Personality & communication
    preferred_tone: Mapped[Optional[str]] = mapped_column(Text)
    communication_style: Mapped[Optional[str]] = mapped_column(Text)
    language_patterns: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Preferences
    likes: Mapped[Optional[list]] = mapped_column(JSONB, server_default="'[]'::jsonb")
    dislikes: Mapped[Optional[list]] = mapped_column(JSONB, server_default="'[]'::jsonb")
    topics_of_interest: Mapped[Optional[list]] = mapped_column(JSONB, server_default="'[]'::jsonb")

    # Pain points & goals
    pain_points: Mapped[Optional[list]] = mapped_column(JSONB, server_default="'[]'::jsonb")
    expectations: Mapped[Optional[list]] = mapped_column(JSONB, server_default="'[]'::jsonb")
    goals: Mapped[Optional[list]] = mapped_column(JSONB, server_default="'[]'::jsonb")

    # Workflow preferences
    preferred_agents: Mapped[Optional[list]] = mapped_column(JSONB, server_default="'[]'::jsonb")
    preferred_workflows: Mapped[Optional[list]] = mapped_column(JSONB, server_default="'[]'::jsonb")
    work_patterns: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Quality signals
    satisfaction_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))
    total_interactions: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    positive_signals: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    negative_signals: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # LLM-generated summaries
    profile_summary: Mapped[Optional[str]] = mapped_column(Text)
    conversation_guide: Mapped[Optional[str]] = mapped_column(Text)

    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    last_analysis_at: Mapped[Optional[datetime]] = _ts_now_nullable()
    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = _ts_now()

    def __repr__(self) -> str:
        return f"<UserProfileIntel user={self.user_id}>"


class UserInsight(Base):
    """Atomic insight extracted from a single interaction."""
    __tablename__ = "user_insights"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(String(255))
    agent_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    source_message: Mapped[Optional[str]] = mapped_column(Text)

    insight_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    insight_value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2), default=Decimal("0.80"))
    sentiment: Mapped[Optional[str]] = mapped_column(String(20))

    is_processed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    processed_at: Mapped[Optional[datetime]] = _ts_now_nullable()

    created_at: Mapped[datetime] = _ts_now()

    def __repr__(self) -> str:
        return f"<UserInsight {self.insight_type}: {self.insight_value[:40]}>"


class BusinessInsight(Base):
    """Cross-user pattern detected from aggregated insights."""
    __tablename__ = "business_insights"

    id: Mapped[uuid.UUID] = _uuid_pk()

    insight_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[Optional[list]] = mapped_column(JSONB, server_default="'[]'::jsonb")
    user_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    frequency: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    impact_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2), default=Decimal("0.50"))

    recommended_actions: Mapped[Optional[list]] = mapped_column(JSONB, server_default="'[]'::jsonb")
    status: Mapped[str] = mapped_column(String(50), default="new", server_default="'new'")
    actioned_at: Mapped[Optional[datetime]] = _ts_now_nullable()

    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = _ts_now()

    def __repr__(self) -> str:
        return f"<BusinessInsight {self.title[:40]}>"


class ContentIdea(Base):
    """Content idea generated from user/business insights."""
    __tablename__ = "content_ideas"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String(100))
    target_audience: Mapped[Optional[str]] = mapped_column(Text)
    hooks: Mapped[Optional[list]] = mapped_column(JSONB, server_default="'[]'::jsonb")
    key_points: Mapped[Optional[list]] = mapped_column(JSONB, server_default="'[]'::jsonb")

    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_insights: Mapped[Optional[list]] = mapped_column(JSONB, server_default="'[]'::jsonb")
    business_insight_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))

    priority: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    status: Mapped[str] = mapped_column(String(50), default="idea", server_default="'idea'")

    created_at: Mapped[datetime] = _ts_now()
    updated_at: Mapped[datetime] = _ts_now()

    def __repr__(self) -> str:
        return f"<ContentIdea {self.title[:40]}>"


# ============================================================================
# AGENT EVOLUTION ENGINE (task 003)
# ============================================================================

class FounderContextModel(Base):
    """A structured, versioned model of a founder's business, distilled from
    FounderProfile + UserProfileIntel. Consumed by the AgentGenerator to regenerate
    agent definitions. See docs/agent-evolution.md."""
    __tablename__ = "founder_context_models"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # {business_model, customer_profile, market_profile, operating_style,
    #  risk_tolerance, goals, summary}
    model: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = _ts_now()

    def __repr__(self) -> str:
        return f"<FounderContextModel user={self.user_id} v{self.version}>"


class AgentDefinition(Base):
    """A versioned, per-founder regeneration of an agent's full definition (system
    prompt + decision framework + tool selection). Staged as ``proposed``; the founder
    approves to make it ``active``; the registry prefers the active row over the global
    agents row. See docs/decisions.md ADR-006."""
    __tablename__ = "agent_definitions"
    __table_args__ = (
        Index("ix_agent_definitions_user_agent_status", "user_id", "agent_name", "status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    decision_framework: Mapped[Optional[str]] = mapped_column(Text)
    selected_tools: Mapped[Optional[list]] = mapped_column(JSONB)

    # proposed | active | superseded
    status: Mapped[str] = mapped_column(String(20), default="proposed", server_default="proposed")
    context_model_version: Mapped[Optional[int]] = mapped_column(Integer)

    created_at: Mapped[datetime] = _ts_now()
    approved_at: Mapped[Optional[datetime]] = _ts_now_nullable()

    def __repr__(self) -> str:
        return f"<AgentDefinition {self.agent_name} user={self.user_id} v{self.version} {self.status}>"
