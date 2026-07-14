"""workflow engine: reconcile workflow* tables + n8n_workflow_id + step_state

Revision ID: 0001_workflow_engine
Revises: 0000_baseline
Create Date: 2026-06-18

ADR-008 / Track B (data layer). This migration is **idempotent / reconciling**,
not a naive create_table: the `workflow_templates`, `workflows`,
`workflow_executions`, `tasks`, `task_dependencies` tables already exist in both
`app/models.py` (ORM) and `schema.sql` (DDL), but `alembic/versions/` was empty —
so a `schema.sql`-seeded DB already has them while a clean Alembic-only DB would not.

Strategy (safe on both):
  - Inspect the live schema. Create each workflow* table only when it is ABSENT
    (green-field) AND its FK dependencies (`users`, `agents`, `workflow_templates`)
    are present — never blindly, so we don't collide with a schema.sql seed and
    don't create a dangling FK on a partially-built DB.
  - Always reconcile the two genuinely-new columns
    (`workflows.n8n_workflow_id`, `workflow_executions.step_state`) with an
    add-if-missing guard, so they land on a schema.sql-seeded DB too.

The migration is the authoritative source for the schema delta (CLAUDE.md §5.8);
schema.sql is kept in sync only as a secondary artifact.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_workflow_engine"
down_revision = "0000_baseline"
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


def _create_workflow_templates() -> None:
    op.create_table(
        "workflow_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
        sa.Column("category", sa.String(100)),
        sa.Column("steps", postgresql.JSONB(), nullable=False),
        sa.Column("trigger_type", sa.String(50)),
        sa.Column("trigger_config", postgresql.JSONB()),
        sa.Column("estimated_duration_minutes", sa.Integer()),
        sa.Column("is_public", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("is_featured", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("usage_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )


def _create_workflows() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workflow_templates.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("steps", postgresql.JSONB(), nullable=False),
        sa.Column("is_scheduled", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("schedule_cron", sa.String(100)),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("total_runs", sa.Integer(), server_default=sa.text("0")),
        sa.Column("successful_runs", sa.Integer(), server_default=sa.text("0")),
        sa.Column("n8n_workflow_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )


def _create_workflow_executions() -> None:
    op.create_table(
        "workflow_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(50), server_default=sa.text("'pending'")),
        sa.Column("trigger_type", sa.String(50)),
        sa.Column("triggered_by", postgresql.JSONB()),
        sa.Column("current_step", sa.Integer(), server_default=sa.text("0")),
        sa.Column("total_steps", sa.Integer(), nullable=False),
        sa.Column("steps_completed", sa.Integer(), server_default=sa.text("0")),
        sa.Column("steps_failed", sa.Integer(), server_default=sa.text("0")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("output_summary", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("step_state", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )


def _create_tasks() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("workflow_execution_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workflow_executions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("task_type", sa.String(100)),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("input_data", postgresql.JSONB()),
        sa.Column("output_data", postgresql.JSONB()),
        sa.Column("status", sa.String(50), server_default=sa.text("'pending'")),
        sa.Column("priority", sa.Integer(), server_default=sa.text("5")),
        sa.Column("requires_approval", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("approval_notes", sa.Text()),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("3")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("tokens_used", sa.Integer()),
        sa.Column("cost_usd", sa.Numeric(10, 4)),
        sa.Column("error_message", sa.Text()),
        sa.Column("error_details", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )


def _create_task_dependencies() -> None:
    op.create_table(
        "task_dependencies",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuid_generate_v4()"), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("depends_on_task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dependency_type", sa.String(50), server_default=sa.text("'blocking'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("task_id", "depends_on_task_id"),
    )


# Ordered (parent → child); each creator runs only if its own table is absent and
# its FK targets exist. `users`/`agents` are owned by the base schema (schema.sql),
# not this migration — Track B scope is the workflow* tables only.
_TABLE_BUILDERS = [
    ("workflow_templates", {"users"}, _create_workflow_templates),
    ("workflows", {"users", "workflow_templates"}, _create_workflows),
    ("workflow_executions", {"users", "workflows"}, _create_workflow_executions),
    ("tasks", {"users", "agents", "workflow_executions"}, _create_tasks),
    ("task_dependencies", {"tasks"}, _create_task_dependencies),
]


def upgrade() -> None:
    # 1) Green-field create — only for tables that are absent and whose FK deps exist.
    for table, deps, builder in _TABLE_BUILDERS:
        if _has_table(table):
            continue
        if all(_has_table(d) for d in deps):
            builder()

    # 2) Reconcile the two genuinely-new columns (safe on a schema.sql-seeded DB too).
    if _has_table("workflows") and not _has_column("workflows", "n8n_workflow_id"):
        op.add_column("workflows", sa.Column("n8n_workflow_id", sa.String(255), nullable=True))
    if _has_table("workflow_executions") and not _has_column("workflow_executions", "step_state"):
        op.add_column("workflow_executions", sa.Column("step_state", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    # Only reverse the additive column delta this migration introduces; never drop the
    # shared workflow* tables (they predate Alembic and may be schema.sql-owned).
    if _has_column("workflow_executions", "step_state"):
        op.drop_column("workflow_executions", "step_state")
    if _has_column("workflows", "n8n_workflow_id"):
        op.drop_column("workflows", "n8n_workflow_id")
