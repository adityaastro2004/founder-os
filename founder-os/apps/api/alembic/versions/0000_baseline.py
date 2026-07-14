"""baseline: frozen full-schema snapshot — single-source DB bootstrap

Revision ID: 0000_baseline
Revises:
Create Date: 2026-07-11

ADR-011 / task 016. This is the re-rooted **baseline**: a frozen snapshot of the
complete schema as of 2026-07-11, inlined from three sources — the ORM metadata
(`app/models.py`, `app/planner_models_db.py`; DDL generated once via autogenerate,
then frozen), `schema.sql` (extensions, indexes, functions, triggers, views, seeds)
and the retired `migrations/002..005*.sql` files (planner/memory/chat/intelligence/
research DDL, `memory_temporal_score`). The four State Engine tables are **not**
here — `0002_state_engine` owns their create + downgrade.

This migration never imports `app.*`: models drift, migrations are frozen history
(same principle as 0001). It is idempotent on every starting state:
  - empty DB           → creates everything in FK order (then 0001/0002 run on top)
  - schema.sql-seeded  → `_has_table` guards skip existing tables; the reconcile
    pass adds ORM-only columns (`founder_profiles.primary_goal_description` — the
    2026-07-11 incident column); seeds hit ON CONFLICT DO NOTHING
  - already at head    → alembic never executes this revision (it is an ancestor)

Note: `CREATE EXTENSION` requires superuser. The docker image, CI service and
current prod all satisfy this; managed Postgres (RDS-style) may need `uuid-ossp`,
`pg_trgm` and `vector` pre-enabled by the operator.

The three research tables (`research_runs`, `tracked_competitors`,
`research_sources`) are dead code today (no app references) but exist in prod —
kept for parity; dropping them is a future task.

Known asymmetry (accepted — reviewer nit 016/1): on a legacy schema.sql-seeded DB
the per-table guard skips the whole branch, so the two 005-era indexes on
schema.sql-owned tables (`idx_tasks_user_status`, `idx_knowledge_items_processing`)
are not created there. Fresh DBs and the hand-rebuilt prod have them; reconciling
legacy DBs is a future follow-up.

`downgrade()` is deliberately a no-op: this is the root revision and may cover
schema that pre-existed alembic — a destructive reverse is never safe (same
philosophy as 0001's downgrade).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0000_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    return any(c["name"] == column for c in _inspector().get_columns(table))


# ────────────────────────────────────────────────────────────────────────────
# Guarded table creators, one per table, each with its indexes in the same
# branch (if the table pre-exists from schema.sql, its indexes exist too).
# Column DDL is the one-time autogenerate output from the ORM metadata; index
# DDL is verbatim from schema.sql / migrations/002..005 (prod parity).
# ────────────────────────────────────────────────────────────────────────────

def _create_users() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("clerk_user_id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("subscription_tier", sa.String(length=50), server_default="free", nullable=False),
        sa.Column("subscription_status", sa.String(length=50), server_default="trial", nullable=False),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
        sa.Column("monthly_task_limit", sa.Integer(), server_default="100", nullable=False),
        sa.Column("monthly_tasks_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_reset_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("clerk_user_id"),
        sa.UniqueConstraint("email"),
    )
    op.execute("CREATE INDEX idx_users_email ON users(email)")
    op.execute("CREATE INDEX idx_users_clerk_id ON users(clerk_user_id)")
    op.execute("CREATE INDEX idx_users_subscription_status ON users(subscription_status)")


def _create_founder_profiles() -> None:
    op.create_table(
        "founder_profiles",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("business_name", sa.String(length=255), nullable=True),
        sa.Column("business_type", sa.String(length=100), nullable=True),
        sa.Column("business_stage", sa.String(length=100), nullable=True),
        sa.Column("industry", sa.String(length=100), nullable=True),
        sa.Column("target_audience", sa.Text(), nullable=True),
        sa.Column("primary_goal", sa.String(length=100), nullable=True),
        sa.Column("primary_goal_description", sa.Text(), nullable=True),
        sa.Column("current_mrr", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("current_users", sa.Integer(), nullable=True),
        sa.Column("monthly_traffic", sa.Integer(), nullable=True),
        sa.Column("working_hours", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("preferred_communication", sa.String(length=50), nullable=True),
        sa.Column("writing_voice", sa.Text(), nullable=True),
        sa.Column("team_size", sa.Integer(), server_default="1", nullable=False),
        sa.Column("team_roles", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_agents() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("temperature", sa.Numeric(precision=3, scale=2), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("available_tools", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("version", sa.String(length=20), server_default="1.0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    # No seed rows: sync_agents_to_db (ADR-004) inserts/updates every AGENT_CLASSES
    # entry at app startup — seeding here would duplicate that mechanism.


def _create_user_agent_configs() -> None:
    op.create_table(
        "user_agent_configs",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("agent_id", sa.UUID(), nullable=False),
        sa.Column("custom_instructions", sa.Text(), nullable=True),
        sa.Column("tone_adjustments", sa.Text(), nullable=True),
        sa.Column("example_outputs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("auto_execute", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "agent_id"),
    )


def _create_workflow_templates() -> None:
    op.create_table(
        "workflow_templates",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("trigger_type", sa.String(length=50), nullable=True),
        sa.Column("trigger_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("estimated_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("is_public", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_featured", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("usage_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )


def _create_workflows() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_scheduled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("schedule_cron", sa.String(length=100), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("total_runs", sa.Integer(), server_default="0", nullable=False),
        sa.Column("successful_runs", sa.Integer(), server_default="0", nullable=False),
        sa.Column("n8n_workflow_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["template_id"], ["workflow_templates.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("CREATE INDEX idx_workflows_user_id ON workflows(user_id)")
    op.execute("CREATE INDEX idx_workflows_next_run_at ON workflows(next_run_at) WHERE is_scheduled = true")


def _create_workflow_executions() -> None:
    op.create_table(
        "workflow_executions",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("workflow_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="pending", nullable=False),
        sa.Column("trigger_type", sa.String(length=50), nullable=True),
        sa.Column("triggered_by", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("current_step", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_steps", sa.Integer(), nullable=False),
        sa.Column("steps_completed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("steps_failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("output_summary", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("step_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("CREATE INDEX idx_workflow_executions_workflow_id ON workflow_executions(workflow_id)")
    op.execute("CREATE INDEX idx_workflow_executions_status ON workflow_executions(status)")
    op.execute("CREATE INDEX idx_workflow_executions_created_at ON workflow_executions(created_at DESC)")


def _create_tasks() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("workflow_execution_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("agent_id", sa.UUID(), nullable=False),
        sa.Column("task_type", sa.String(length=100), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("input_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=50), server_default="pending", nullable=False),
        sa.Column("priority", sa.Integer(), server_default="5", nullable=False),
        sa.Column("requires_approval", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("approved_by", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_notes", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_execution_id"], ["workflow_executions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("CREATE INDEX idx_tasks_user_id ON tasks(user_id)")
    op.execute("CREATE INDEX idx_tasks_status ON tasks(status)")
    op.execute("CREATE INDEX idx_tasks_created_at ON tasks(created_at DESC)")
    op.execute("CREATE INDEX idx_tasks_workflow_execution_id ON tasks(workflow_execution_id)")
    op.execute("CREATE INDEX idx_tasks_agent_id ON tasks(agent_id)")
    op.execute("CREATE INDEX idx_tasks_user_status ON tasks (user_id, status, created_at DESC)")


def _create_task_dependencies() -> None:
    op.create_table(
        "task_dependencies",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("depends_on_task_id", sa.UUID(), nullable=False),
        sa.Column("dependency_type", sa.String(length=50), server_default="blocking", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["depends_on_task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "depends_on_task_id"),
    )


def _create_knowledge_items() -> None:
    op.create_table(
        "knowledge_items",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("tags", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("times_referenced", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_referenced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("processing_status", sa.String(length=50), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("CREATE INDEX idx_knowledge_items_user_id ON knowledge_items(user_id)")
    # schema.sql's definition wins the idx_knowledge_items_category name; 005's
    # same-named (user_id, category) partial index never applied (IF NOT EXISTS).
    op.execute("CREATE INDEX idx_knowledge_items_category ON knowledge_items(category)")
    op.execute("CREATE INDEX idx_knowledge_items_tags ON knowledge_items USING GIN(tags)")
    op.execute(
        "CREATE INDEX idx_knowledge_items_content_search ON knowledge_items "
        "USING gin(to_tsvector('english', content))"
    )
    # pgvector index (ivfflat) — rebuild with more lists when data grows
    op.execute(
        "CREATE INDEX knowledge_items_embedding_idx ON knowledge_items "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
    op.execute(
        "CREATE INDEX idx_knowledge_items_processing ON knowledge_items (processing_status) "
        "WHERE processing_status != 'completed'"
    )


def _create_context_usage() -> None:
    op.create_table(
        "context_usage",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("knowledge_item_id", sa.UUID(), nullable=False),
        sa.Column("relevance_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("was_useful", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["knowledge_item_id"], ["knowledge_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_business_metrics() -> None:
    op.create_table(
        "business_metrics",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("metric_type", sa.String(length=100), nullable=True),
        sa.Column("metric_value", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("metric_unit", sa.String(length=50), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("CREATE INDEX idx_business_metrics_user_id ON business_metrics(user_id)")
    op.execute("CREATE INDEX idx_business_metrics_type_date ON business_metrics(metric_type, period_start)")


def _create_integrations() -> None:
    op.create_table(
        "integrations",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("integration_type", sa.String(length=100), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("scopes", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(length=50), nullable=True),
        sa.Column("sync_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "integration_type"),
    )
    op.execute("CREATE INDEX idx_integrations_user_id ON integrations(user_id)")
    op.execute("CREATE INDEX idx_integrations_type ON integrations(integration_type)")


def _create_integration_syncs() -> None:
    op.create_table(
        "integration_syncs",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("integration_id", sa.UUID(), nullable=False),
        sa.Column("sync_type", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("records_synced", sa.Integer(), server_default="0", nullable=False),
        sa.Column("records_failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_outputs() -> None:
    op.create_table(
        "outputs",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("output_type", sa.String(length=100), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("format", sa.String(length=50), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("estimated_read_time_minutes", sa.Integer(), nullable=True),
        sa.Column("publish_status", sa.String(length=50), server_default="draft", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_to", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("external_urls", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("parent_output_id", sa.UUID(), nullable=True),
        sa.Column("user_rating", sa.Integer(), nullable=True),
        sa.Column("user_feedback", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("user_rating >= 1 AND user_rating <= 5"),
        sa.ForeignKeyConstraint(["parent_output_id"], ["outputs.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("CREATE INDEX idx_outputs_task_id ON outputs(task_id)")
    op.execute("CREATE INDEX idx_outputs_user_id ON outputs(user_id)")
    op.execute("CREATE INDEX idx_outputs_type ON outputs(output_type)")
    op.execute("CREATE INDEX idx_outputs_status ON outputs(publish_status)")


def _create_agent_analytics() -> None:
    op.create_table(
        "agent_analytics",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("agent_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("tasks_completed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tasks_failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("average_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("average_tokens_used", sa.Integer(), nullable=True),
        sa.Column("total_cost_usd", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("approval_rate", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("average_user_rating", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "user_id", "metric_date"),
    )


def _create_task_feedback() -> None:
    op.create_table(
        "task_feedback",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("feedback_type", sa.String(length=50), nullable=True),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("action_taken", sa.String(length=50), nullable=True),
        sa.Column("edits_made", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("rating >= 1 AND rating <= 5"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_learning_insights() -> None:
    op.create_table(
        "learning_insights",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("agent_id", sa.UUID(), nullable=False),
        sa.Column("insight_type", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("pattern_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("occurrences", sa.Integer(), server_default="1", nullable=False),
        sa.Column("improvement_action", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_notifications() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("notification_type", sa.String(length=100), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("action_url", sa.Text(), nullable=True),
        sa.Column("related_entity_type", sa.String(length=50), nullable=True),
        sa.Column("related_entity_id", sa.UUID(), nullable=True),
        sa.Column("is_read", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_via", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("CREATE INDEX idx_notifications_user_id ON notifications(user_id)")
    op.execute("CREATE INDEX idx_notifications_is_read ON notifications(is_read) WHERE is_read = false")
    op.execute("CREATE INDEX idx_notifications_created_at ON notifications(created_at DESC)")


def _create_notification_preferences() -> None:
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("email_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("slack_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("push_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text(
                '\'{\n        "task_completed": true,\n        "approval_needed": true,'
                '\n        "workflow_failed": true,\n        "weekly_summary": true,'
                '\n        "tips_and_insights": false\n    }\'::jsonb'
            ),
            nullable=True,
        ),
        sa.Column("quiet_hours_start", sa.Time(), nullable=True),
        sa.Column("quiet_hours_end", sa.Time(), nullable=True),
        sa.Column("quiet_hours_timezone", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )


def _create_subscription_plans() -> None:
    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price_monthly_usd", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("price_yearly_usd", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("monthly_task_limit", sa.Integer(), nullable=True),
        sa.Column("agent_limit", sa.Integer(), nullable=True),
        sa.Column("workflow_limit", sa.Integer(), nullable=True),
        sa.Column("knowledge_items_limit", sa.Integer(), nullable=True),
        sa.Column("team_members_limit", sa.Integer(), nullable=True),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )


def _create_usage_records() -> None:
    op.create_table(
        "usage_records",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("usage_type", sa.String(length=100), nullable=True),
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("billing_period_start", sa.Date(), nullable=True),
        sa.Column("billing_period_end", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_audit_logs() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=True),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("success", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id)")
    op.execute("CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id)")
    op.execute("CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at DESC)")


def _create_api_keys() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("key_hash", sa.String(length=255), nullable=False),
        sa.Column("key_prefix", sa.String(length=20), nullable=True),
        sa.Column("scopes", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("usage_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )


def _create_founder_context_models() -> None:
    op.create_table(
        "founder_context_models",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("model", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("CREATE INDEX ix_founder_context_models_user ON founder_context_models(user_id)")


def _create_agent_definitions() -> None:
    op.create_table(
        "agent_definitions",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("agent_name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("decision_framework", sa.Text(), nullable=True),
        sa.Column("selected_tools", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="proposed", nullable=False),
        sa.Column("context_model_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("CREATE INDEX ix_agent_definitions_user ON agent_definitions(user_id)")
    op.execute(
        "CREATE INDEX ix_agent_definitions_user_agent_status "
        "ON agent_definitions(user_id, agent_name, status)"
    )


def _create_planner_users() -> None:
    op.create_table(
        "planner_users",
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), server_default="", nullable=False),
        sa.Column("business_name", sa.String(length=255), server_default="", nullable=False),
        sa.Column("business_type", sa.String(length=100), server_default="", nullable=False),
        sa.Column("business_stage", sa.String(length=100), server_default="", nullable=False),
        sa.Column("industry", sa.String(length=100), server_default="", nullable=False),
        sa.Column("target_audience", sa.Text(), server_default="", nullable=False),
        sa.Column("team_size", sa.Integer(), server_default="1", nullable=False),
        sa.Column("current_mrr", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False),
        sa.Column("current_users", sa.Integer(), server_default="0", nullable=False),
        sa.Column("mrr_growth_pct", sa.Numeric(precision=5, scale=2), server_default="0", nullable=False),
        sa.Column("primary_goal", sa.Text(), server_default="", nullable=False),
        sa.Column("goals_this_week", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=True),
        sa.Column("completed_last_week", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=True),
        sa.Column("blockers", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=True),
        sa.Column("custom_instructions", sa.Text(), server_default="", nullable=False),
        sa.Column("timezone", sa.String(length=50), server_default="Asia/Kolkata", nullable=False),
        sa.Column("preferred_work_hours", sa.String(length=20), server_default="09:00-18:00", nullable=False),
        sa.Column("calendar_id", sa.String(length=255), server_default="primary", nullable=False),
        sa.Column("gcal_connected", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("gcal_access_token", sa.Text(), nullable=True),
        sa.Column("gcal_refresh_token", sa.Text(), nullable=True),
        sa.Column("gcal_token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gcal_token_data", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=True),
        sa.Column("plan_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_plan_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_plan_events", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.execute(
        "CREATE INDEX idx_planner_users_gcal ON planner_users(gcal_connected) "
        "WHERE gcal_connected = TRUE"
    )


def _create_plan_history() -> None:
    op.create_table(
        "plan_history",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("plan_id", sa.String(length=50), nullable=True),
        sa.Column("week_of", sa.Date(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("task_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("events_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("events_failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duration_seconds", sa.Numeric(precision=6, scale=1), nullable=True),
        sa.Column("top_priorities", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=True),
        sa.Column("plan_data", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=True),
        sa.Column("gcal_events", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["planner_users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("CREATE INDEX idx_plan_history_user ON plan_history(user_id, generated_at DESC)")


def _create_memory_pages() -> None:
    op.create_table(
        "memory_pages",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("page_type", sa.String(length=50), server_default="event", nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("access_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("importance", sa.Numeric(precision=4, scale=3), server_default="0.500", nullable=False),
        sa.Column("decay_rate", sa.Numeric(precision=6, scale=5), server_default="0.00100", nullable=False),
        sa.Column("is_pinned", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_interval_days", sa.Integer(), nullable=True),
        sa.Column("review_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chapter", sa.String(length=100), nullable=True),
        sa.Column("tags", sa.ARRAY(sa.Text()), server_default="{}", nullable=True),
        sa.Column("entities", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=True),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("related_ids", sa.ARRAY(sa.UUID()), server_default="{}", nullable=True),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("source", sa.String(length=100), server_default="user_input", nullable=False),
        sa.Column("metadata_", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["memory_pages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    # migrations/002 index set (temporal / chapter / review / importance / type /
    # ivfflat / fts / tags / entities) …
    op.execute(
        "CREATE INDEX idx_memory_user_occurred ON memory_pages(user_id, occurred_at DESC) "
        "WHERE is_active = TRUE"
    )
    op.execute(
        "CREATE INDEX idx_memory_user_chapter ON memory_pages(user_id, chapter, occurred_at DESC) "
        "WHERE is_active = TRUE"
    )
    op.execute(
        "CREATE INDEX idx_memory_review_due ON memory_pages(next_review_at) "
        "WHERE next_review_at IS NOT NULL AND is_active = TRUE"
    )
    op.execute(
        "CREATE INDEX idx_memory_importance ON memory_pages(user_id, importance DESC) "
        "WHERE is_active = TRUE"
    )
    op.execute(
        "CREATE INDEX idx_memory_user_type ON memory_pages(user_id, page_type, occurred_at DESC) "
        "WHERE is_active = TRUE"
    )
    op.execute(
        "CREATE INDEX idx_memory_embedding ON memory_pages "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 20)"
    )
    op.execute(
        "CREATE INDEX idx_memory_content_fts ON memory_pages "
        "USING gin(to_tsvector('english', content))"
    )
    op.execute("CREATE INDEX idx_memory_tags ON memory_pages USING gin(tags)")
    op.execute("CREATE INDEX idx_memory_entities ON memory_pages USING gin(entities jsonb_path_ops)")
    # … plus the migrations/005 performance set (kept despite overlap — prod parity).
    op.execute(
        "CREATE INDEX idx_memory_pages_user_occurred ON memory_pages (user_id, occurred_at DESC) "
        "WHERE is_active = TRUE"
    )
    op.execute(
        "CREATE INDEX idx_memory_pages_user_chapter ON memory_pages (user_id, chapter, occurred_at DESC) "
        "WHERE is_active = TRUE AND chapter IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX idx_memory_pages_review_due ON memory_pages (user_id, next_review_at) "
        "WHERE next_review_at IS NOT NULL AND is_active = TRUE"
    )


def _create_memory_links() -> None:
    op.create_table(
        "memory_links",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("link_type", sa.String(length=50), server_default="related", nullable=False),
        sa.Column("strength", sa.Numeric(precision=3, scale=2), server_default="0.50", nullable=False),
        sa.Column("metadata_", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["memory_pages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["memory_pages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "target_id", "link_type"),
    )
    op.execute("CREATE INDEX idx_memory_links_source ON memory_links(source_id)")
    op.execute("CREATE INDEX idx_memory_links_target ON memory_links(target_id)")


def _create_agent_runs() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("agent_name", sa.String(length=100), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("agent_response", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("tokens_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("duration_seconds", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("stop_reason", sa.String(length=50), nullable=True),
        sa.Column("tool_names", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tool_calls_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("agents_used", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("delegations_made", sa.Integer(), server_default="0", nullable=False),
        sa.Column("delegation_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=50), server_default="completed", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("CREATE INDEX idx_agent_runs_user_id ON agent_runs(user_id)")
    op.execute("CREATE INDEX idx_agent_runs_agent_name ON agent_runs(agent_name)")
    op.execute("CREATE INDEX idx_agent_runs_session_id ON agent_runs(session_id)")
    op.execute("CREATE INDEX idx_agent_runs_created_at ON agent_runs(created_at DESC)")
    op.execute("CREATE INDEX idx_agent_runs_user_agent ON agent_runs(user_id, agent_name, created_at DESC)")
    op.execute("CREATE INDEX idx_agent_runs_user_session ON agent_runs (user_id, session_id, created_at DESC)")


def _create_chat_messages() -> None:
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("agent_name", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("tool_names", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("agents_used", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("delegations_made", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=50), server_default="completed", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("CREATE INDEX idx_chat_messages_user_id ON chat_messages(user_id)")
    op.execute("CREATE INDEX idx_chat_messages_session_id ON chat_messages(session_id)")
    op.execute("CREATE INDEX idx_chat_messages_agent_name ON chat_messages(agent_name)")
    op.execute(
        "CREATE INDEX idx_chat_messages_user_session ON chat_messages(user_id, session_id, created_at ASC)"
    )
    op.execute(
        "CREATE INDEX idx_chat_messages_user_agent ON chat_messages(user_id, agent_name, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX idx_chat_messages_session ON chat_messages (user_id, session_id, agent_name, created_at DESC)"
    )


def _create_user_profiles_intel() -> None:
    op.create_table(
        "user_profiles_intel",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("preferred_tone", sa.Text(), nullable=True),
        sa.Column("communication_style", sa.Text(), nullable=True),
        sa.Column("language_patterns", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("likes", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=True),
        sa.Column("dislikes", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=True),
        sa.Column("topics_of_interest", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=True),
        sa.Column("pain_points", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=True),
        sa.Column("expectations", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=True),
        sa.Column("goals", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=True),
        sa.Column("preferred_agents", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=True),
        sa.Column("preferred_workflows", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=True),
        sa.Column("work_patterns", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("satisfaction_score", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("total_interactions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("positive_signals", sa.Integer(), server_default="0", nullable=False),
        sa.Column("negative_signals", sa.Integer(), server_default="0", nullable=False),
        sa.Column("profile_summary", sa.Text(), nullable=True),
        sa.Column("conversation_guide", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("last_analysis_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_profiles_intel_user"),
    )
    op.execute("CREATE INDEX idx_user_profiles_intel_user ON user_profiles_intel(user_id)")


def _create_user_insights() -> None:
    op.create_table(
        "user_insights",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("agent_name", sa.String(length=100), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("agent_run_id", sa.UUID(), nullable=True),
        sa.Column("source_message", sa.Text(), nullable=True),
        sa.Column("insight_type", sa.String(length=50), nullable=False),
        sa.Column("insight_value", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("sentiment", sa.String(length=20), nullable=True),
        sa.Column("is_processed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("CREATE INDEX idx_user_insights_user ON user_insights(user_id)")
    op.execute("CREATE INDEX idx_user_insights_type ON user_insights(insight_type)")
    op.execute(
        "CREATE INDEX idx_user_insights_unprocessed ON user_insights(user_id, is_processed) "
        "WHERE NOT is_processed"
    )
    op.execute("CREATE INDEX idx_user_insights_created ON user_insights(created_at DESC)")


def _create_business_insights() -> None:
    op.create_table(
        "business_insights",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("insight_type", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=True),
        sa.Column("user_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("frequency", sa.Integer(), server_default="1", nullable=False),
        sa.Column("impact_score", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("recommended_actions", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=True),
        sa.Column("status", sa.String(length=50), server_default="new", nullable=False),
        sa.Column("actioned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("CREATE INDEX idx_business_insights_type ON business_insights(insight_type)")
    op.execute("CREATE INDEX idx_business_insights_impact ON business_insights(impact_score DESC)")


def _create_content_ideas() -> None:
    op.create_table(
        "content_ideas",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("target_audience", sa.Text(), nullable=True),
        sa.Column("hooks", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=True),
        sa.Column("key_points", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_insights", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=True),
        sa.Column("business_insight_id", sa.UUID(), nullable=True),
        sa.Column("priority", sa.Integer(), server_default="5", nullable=False),
        sa.Column("status", sa.String(length=50), server_default="idea", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("CREATE INDEX idx_content_ideas_user ON content_ideas(user_id)")
    op.execute("CREATE INDEX idx_content_ideas_status ON content_ideas(status)")
    op.execute("CREATE INDEX idx_content_ideas_priority ON content_ideas(priority DESC)")


# ── Non-ORM research tables, verbatim from migrations/005 (dead code today —
#    crawler_routes stores competitors in memory_pages — kept for prod parity;
#    dropping them is a future task). ─────────────────────────────────────────

def _create_research_runs() -> None:
    op.execute("""
        CREATE TABLE research_runs (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id         VARCHAR(255) NOT NULL,
            status          VARCHAR(50)  NOT NULL DEFAULT 'running',
            started_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            completed_at    TIMESTAMPTZ,
            duration_seconds NUMERIC(8,1),
            queries_executed   INTEGER NOT NULL DEFAULT 0,
            pages_crawled      INTEGER NOT NULL DEFAULT 0,
            findings_stored    INTEGER NOT NULL DEFAULT 0,
            competitor_updates JSONB NOT NULL DEFAULT '[]',
            trends             JSONB NOT NULL DEFAULT '[]',
            customer_signals   JSONB NOT NULL DEFAULT '[]',
            error_message      TEXT,
            profile_snapshot   JSONB NOT NULL DEFAULT '{}',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_research_runs_user ON research_runs (user_id, started_at DESC)")


def _create_tracked_competitors() -> None:
    op.execute("""
        CREATE TABLE tracked_competitors (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id     VARCHAR(255) NOT NULL,
            name        VARCHAR(255) NOT NULL,
            website     VARCHAR(500),
            notes       TEXT DEFAULT '',
            added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, name)
        )
    """)
    op.execute("CREATE INDEX idx_tracked_competitors_user ON tracked_competitors (user_id)")


def _create_research_sources() -> None:
    op.execute("""
        CREATE TABLE research_sources (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id     VARCHAR(255) NOT NULL,
            name        VARCHAR(255) NOT NULL,
            url         VARCHAR(1000) NOT NULL,
            source_type VARCHAR(50) NOT NULL DEFAULT 'rss',
            is_active   BOOLEAN NOT NULL DEFAULT TRUE,
            added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, url)
        )
    """)
    op.execute(
        "CREATE INDEX idx_research_sources_user ON research_sources (user_id) WHERE is_active = TRUE"
    )


# Ordered parent → child; each creator runs only when its table is absent
# (schema.sql-seeded DBs skip their ~32 tables and fall through to the
# 002–005-era ones). The 4 State Engine tables are 0002's — not listed here.
_TABLE_BUILDERS = [
    ("users", _create_users),
    ("founder_profiles", _create_founder_profiles),
    ("agents", _create_agents),
    ("user_agent_configs", _create_user_agent_configs),
    ("workflow_templates", _create_workflow_templates),
    ("workflows", _create_workflows),
    ("workflow_executions", _create_workflow_executions),
    ("tasks", _create_tasks),
    ("task_dependencies", _create_task_dependencies),
    ("knowledge_items", _create_knowledge_items),
    ("context_usage", _create_context_usage),
    ("business_metrics", _create_business_metrics),
    ("integrations", _create_integrations),
    ("integration_syncs", _create_integration_syncs),
    ("outputs", _create_outputs),
    ("agent_analytics", _create_agent_analytics),
    ("task_feedback", _create_task_feedback),
    ("learning_insights", _create_learning_insights),
    ("notifications", _create_notifications),
    ("notification_preferences", _create_notification_preferences),
    ("subscription_plans", _create_subscription_plans),
    ("usage_records", _create_usage_records),
    ("audit_logs", _create_audit_logs),
    ("api_keys", _create_api_keys),
    ("founder_context_models", _create_founder_context_models),
    ("agent_definitions", _create_agent_definitions),
    ("planner_users", _create_planner_users),
    ("plan_history", _create_plan_history),
    ("memory_pages", _create_memory_pages),
    ("memory_links", _create_memory_links),
    ("agent_runs", _create_agent_runs),
    ("chat_messages", _create_chat_messages),
    ("user_profiles_intel", _create_user_profiles_intel),
    ("user_insights", _create_user_insights),
    ("business_insights", _create_business_insights),
    ("content_ideas", _create_content_ideas),
    ("research_runs", _create_research_runs),
    ("tracked_competitors", _create_tracked_competitors),
    ("research_sources", _create_research_sources),
]


# ────────────────────────────────────────────────────────────────────────────
# Functions / triggers / views — verbatim from schema.sql and migrations/002.
# CREATE OR REPLACE everywhere → identical overwrite on a seeded DB.
# ────────────────────────────────────────────────────────────────────────────

_FN_UPDATE_UPDATED_AT = """
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';
"""

# Load-bearing: 8 call sites in app/memory/manager.py (migrations/002 origin).
_FN_MEMORY_TEMPORAL_SCORE = """
CREATE OR REPLACE FUNCTION memory_temporal_score(
    p_importance NUMERIC,
    p_decay_rate NUMERIC,
    p_occurred_at TIMESTAMP WITH TIME ZONE,
    p_is_pinned BOOLEAN DEFAULT FALSE
) RETURNS NUMERIC AS $$
BEGIN
    IF p_is_pinned THEN
        RETURN p_importance;
    END IF;
    -- Exponential decay: importance * exp(-decay_rate * days_since)
    RETURN p_importance * EXP(
        -p_decay_rate * GREATEST(
            EXTRACT(EPOCH FROM (NOW() - p_occurred_at)) / 86400.0,
            0
        )
    );
END;
$$ LANGUAGE plpgsql IMMUTABLE;
"""

# The ORM has no onupdate on these tables — the triggers ARE the behavior.
_UPDATED_AT_TRIGGER_TABLES = (
    "users", "founder_profiles", "agents", "workflows",
    "tasks", "knowledge_items", "outputs", "integrations",
)

_VIEWS = (
    """
CREATE OR REPLACE VIEW tasks_pending_approval AS
SELECT t.*, a.display_name as agent_name, u.email as user_email
FROM tasks t
JOIN agents a ON t.agent_id = a.id
JOIN users u ON t.user_id = u.id
WHERE t.status = 'awaiting_approval'
AND t.requires_approval = true
ORDER BY t.created_at DESC;
""",
    """
CREATE OR REPLACE VIEW user_dashboard_summary AS
SELECT
    u.id as user_id,
    u.email,
    u.subscription_tier,
    COUNT(DISTINCT t.id) FILTER (WHERE t.created_at > NOW() - INTERVAL '7 days') as tasks_last_7_days,
    COUNT(DISTINCT t.id) FILTER (WHERE t.status = 'awaiting_approval') as tasks_pending_approval,
    COUNT(DISTINCT w.id) as total_workflows,
    COUNT(DISTINCT w.id) FILTER (WHERE w.is_scheduled = true) as scheduled_workflows,
    COUNT(DISTINCT ki.id) as knowledge_items,
    u.monthly_tasks_used,
    u.monthly_task_limit
FROM users u
LEFT JOIN tasks t ON u.id = t.user_id
LEFT JOIN workflows w ON u.id = w.user_id
LEFT JOIN knowledge_items ki ON u.id = ki.user_id
WHERE u.deleted_at IS NULL
GROUP BY u.id;
""",
    """
CREATE OR REPLACE VIEW agent_performance_summary AS
SELECT
    a.id as agent_id,
    a.display_name,
    COUNT(t.id) as total_tasks,
    COUNT(t.id) FILTER (WHERE t.status = 'completed') as completed_tasks,
    COUNT(t.id) FILTER (WHERE t.status = 'failed') as failed_tasks,
    ROUND(AVG(t.duration_seconds)) as avg_duration_seconds,
    ROUND(AVG(t.tokens_used)) as avg_tokens,
    SUM(t.cost_usd) as total_cost
FROM agents a
LEFT JOIN tasks t ON a.id = t.agent_id
WHERE t.created_at > NOW() - INTERVAL '30 days'
GROUP BY a.id, a.display_name;
""",
)


# ────────────────────────────────────────────────────────────────────────────
# Seeds — verbatim from schema.sql + ON CONFLICT DO NOTHING on the verified
# unique keys (workflow_templates.slug, subscription_plans.name). Insert-only;
# never updates existing rows. Raw strings: the JSON contains literal \n.
# ────────────────────────────────────────────────────────────────────────────

_SEED_WORKFLOW_TEMPLATES = r"""
INSERT INTO workflow_templates (name, slug, description, category, steps, trigger_type, estimated_duration_minutes) VALUES
('Weekly Planning', 'weekly-planning',
 'Full weekly planning workflow: review last week, scan the market, generate a prioritised plan, schedule content, and create actionable tasks.',
 'planning',
 '[
    {
      "step_number": 1,
      "agent_name": "ops",
      "title": "Compile Last Week Metrics",
      "task_template": "Pull all business metrics for the past 7 days. Summarise: MRR change, active users, traffic, conversion rate, support ticket volume, and any anomalies. Use the get_business_metrics tool. Output a structured dashboard summary.",
      "depends_on": [],
      "requires_approval": false,
      "timeout_seconds": 120,
      "retry_on_failure": true,
      "max_retries": 2,
      "output_key": "last_week_metrics",
      "tools_required": ["get_business_metrics", "get_current_datetime"]
    },
    {
      "step_number": 2,
      "agent_name": "planner",
      "title": "Review Prior Week Plan",
      "task_template": "Retrieve the previous weeks plan from shared memory (key: current_plan). For each task that was planned: mark it as completed, partially done, or missed. Calculate the completion rate. Identify any recurring blockers. Output a structured review with a carryover_tasks list of items that need to roll into the new week.",
      "depends_on": [],
      "requires_approval": false,
      "timeout_seconds": 120,
      "retry_on_failure": true,
      "max_retries": 2,
      "output_key": "prior_week_review",
      "tools_required": ["list_tasks", "get_current_datetime", "store_working_memory"]
    },
    {
      "step_number": 3,
      "agent_name": "research",
      "title": "Market & Competitor Scan",
      "task_template": "Given the founders industry (from context), run a quick scan for: (1) competitor moves in the last 7 days, (2) relevant market/industry news, (3) trending topics in the founders space. Use web_search. Summarise the top 5 actionable insights. Reference: {{last_week_metrics}}",
      "depends_on": [1],
      "requires_approval": false,
      "timeout_seconds": 180,
      "retry_on_failure": true,
      "max_retries": 2,
      "output_key": "market_scan",
      "tools_required": ["web_search", "search_knowledge"]
    },
    {
      "step_number": 4,
      "agent_name": "planner",
      "title": "Generate Weekly Plan",
      "task_template": "Using the following inputs, create a prioritised weekly plan:\n\n1. Last Week Metrics: {{last_week_metrics}}\n2. Prior Plan Review: {{prior_week_review}} (include carryover tasks)\n3. Market Intelligence: {{market_scan}}\n4. Founder Profile: {{founder_profile}}\n\nOutput format:\n- Top 3 Priorities for the week (with rationale)\n- Daily breakdown (Mon-Fri) with specific tasks, owners (which agent), and time estimates\n- Delegations: list of tasks to delegate to content/research/ops/product/support agents\n- Risks and mitigations\n- Success criteria for the week\n\nSave the plan to shared memory under key current_plan.",
      "depends_on": [1, 2, 3],
      "requires_approval": true,
      "timeout_seconds": 300,
      "retry_on_failure": true,
      "max_retries": 1,
      "output_key": "weekly_plan",
      "tools_required": ["create_task", "store_working_memory", "get_current_datetime", "search_knowledge"]
    },
    {
      "step_number": 5,
      "agent_name": "content",
      "title": "Schedule Content Calendar",
      "task_template": "Based on the weekly plan ({{weekly_plan}}), create a content calendar for the week:\n- Blog posts / articles to write (with topics + target publish day)\n- Social media posts (LinkedIn, Twitter/X) - 1 per day minimum\n- Newsletter if scheduled\n- Any launch announcements\n\nMatch the founders writing voice (use get_writing_style). Save each piece as a draft via save_draft.",
      "depends_on": [4],
      "requires_approval": true,
      "timeout_seconds": 240,
      "retry_on_failure": true,
      "max_retries": 1,
      "output_key": "content_calendar",
      "tools_required": ["save_draft", "get_writing_style", "get_current_datetime"]
    },
    {
      "step_number": 6,
      "agent_name": "ops",
      "title": "Create Tasks & Send Notifications",
      "task_template": "Take the approved weekly plan ({{weekly_plan}}) and:\n1. Create individual task records for each item using create_task\n2. Set priorities (1=urgent, 10=backlog)\n3. Assign each task to the appropriate agent\n4. Generate a summary notification for the founder with the weeks key objectives\n\nOutput: list of created task IDs and the notification content.",
      "depends_on": [4],
      "requires_approval": false,
      "timeout_seconds": 120,
      "retry_on_failure": true,
      "max_retries": 2,
      "output_key": "task_creation_summary",
      "tools_required": ["create_task", "list_tasks", "get_current_datetime"]
    }
 ]'::jsonb,
 'scheduled', 15),
('Content Creation', 'content-creation', 'Research and create blog content', 'marketing',
 '[
    {"step_number": 1, "agent_name": "research", "task_template": "Research topic and gather insights", "requires_approval": false},
    {"step_number": 2, "agent_name": "content", "task_template": "Write blog post draft", "requires_approval": true},
    {"step_number": 3, "agent_name": "content", "task_template": "Create social media posts", "requires_approval": true}
 ]'::jsonb,
 'manual', 20),
('Product Launch', 'product-launch', 'Complete product launch workflow', 'product',
 '[
    {"step_number": 1, "agent_name": "product", "task_template": "Update changelog and documentation", "requires_approval": true},
    {"step_number": 2, "agent_name": "content", "task_template": "Write launch announcement", "requires_approval": true},
    {"step_number": 3, "agent_name": "support", "task_template": "Prepare customer FAQs", "requires_approval": true},
    {"step_number": 4, "agent_name": "ops", "task_template": "Setup tracking metrics", "requires_approval": false}
 ]'::jsonb,
 'manual', 30),
('Customer Onboarding', 'customer-onboarding', 'Automate new customer onboarding flow', 'operations',
 '[
    {"step_number": 1, "agent_name": "support", "task_template": "Generate personalized welcome email", "requires_approval": true},
    {"step_number": 2, "agent_name": "product", "task_template": "Create onboarding checklist", "requires_approval": false},
    {"step_number": 3, "agent_name": "ops", "task_template": "Setup tracking for new customer", "requires_approval": false}
 ]'::jsonb,
 'event', 10)
ON CONFLICT (slug) DO NOTHING;
"""

_SEED_SUBSCRIPTION_PLANS = r"""
INSERT INTO subscription_plans (name, display_name, description, price_monthly_usd, price_yearly_usd,
                                monthly_task_limit, agent_limit, workflow_limit, knowledge_items_limit, team_members_limit, features) VALUES
('free', 'Free Trial', '14-day trial with limited features', 0, 0, 50, 3, 2, 10, 1,
 '["basic_agents", "manual_workflows"]'::jsonb),
('starter', 'Starter', 'For solo founders getting started', 99, 999, 500, 5, 10, 100, 1,
 '["all_agents", "scheduled_workflows", "basic_integrations", "email_support"]'::jsonb),
('pro', 'Pro', 'For growing teams', 299, 2999, 2000, 10, 50, 500, 5,
 '["all_agents", "custom_workflows", "advanced_integrations", "priority_support", "api_access"]'::jsonb),
('enterprise', 'Enterprise', 'Custom solution for larger teams', 999, 9999, 999999, 999, 999, 9999, 50,
 '["all_agents", "custom_workflows", "all_integrations", "dedicated_support", "api_access", "white_label", "sla"]'::jsonb)
ON CONFLICT (name) DO NOTHING;
"""


def upgrade() -> None:
    # 1) Extensions (superuser required — see module docstring).
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')

    # 2) Guarded table creates in FK order, indexes in the same branch.
    for table, builder in _TABLE_BUILDERS:
        if not _has_table(table):
            builder()

    # 3) Functions.
    op.execute(_FN_UPDATE_UPDATED_AT)
    op.execute(_FN_MEMORY_TEMPORAL_SCORE)

    # 4) updated_at triggers (CREATE OR REPLACE TRIGGER — PG16).
    for table in _UPDATED_AT_TRIGGER_TABLES:
        op.execute(
            f"CREATE OR REPLACE TRIGGER update_{table}_updated_at BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()"
        )

    # 5) Views (unused by app code, present in prod).
    for view_sql in _VIEWS:
        op.execute(view_sql)

    # 6) Column-reconcile pass — ORM ⊃ schema.sql deltas on schema.sql-owned
    #    tables (this is what fixes a legacy-seeded DB). Discovered by the
    #    seeded-DB test (tests/migrations), then frozen here.
    if _has_table("founder_profiles") and not _has_column("founder_profiles", "primary_goal_description"):
        op.add_column("founder_profiles", sa.Column("primary_goal_description", sa.Text(), nullable=True))

    # 7) Seeds.
    op.execute(_SEED_WORKFLOW_TEMPLATES)
    op.execute(_SEED_SUBSCRIPTION_PLANS)


def downgrade() -> None:
    # Deliberate no-op: the baseline is the root revision and may cover schema
    # that pre-existed alembic (schema.sql-seeded DBs) — a destructive reverse
    # is never safe, and downgrading below the root is meaningless.
    pass
