"""
Founder OS — Workflow persistence helpers (Track B / ADR-008).

Thin, user-scoped CRUD for `Workflow` and `WorkflowExecution`, reused by the
workflow router, the callback handler, and the runner. Every read and write is
filtered by `user_id` (C-2 user-scoping) — a caller can only ever see/operate
their own workflows and runs. Identity is always the internal `users.id` UUID
(resolved upstream via `app.users.get_or_create_user_id` / a verified token),
never a value taken from a request body.

These helpers `flush` (to populate server-side defaults like ids) but do NOT
commit — the caller's `get_db` dependency owns the transaction boundary.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Workflow, WorkflowExecution


def _as_uuid(value: uuid.UUID | str) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


# ============================================================================
# Workflow
# ============================================================================

async def create_workflow(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | str,
    name: str,
    steps: dict[str, Any],
    description: Optional[str] = None,
    is_scheduled: bool = False,
    schedule_cron: Optional[str] = None,
    n8n_workflow_id: Optional[str] = None,
) -> Workflow:
    """Create a Workflow owned by `user_id`. `steps` is the serialized IR envelope."""
    workflow = Workflow(
        user_id=_as_uuid(user_id),
        name=name,
        description=description,
        steps=steps,
        is_scheduled=is_scheduled,
        schedule_cron=schedule_cron,
        n8n_workflow_id=n8n_workflow_id,
    )
    db.add(workflow)
    await db.flush()
    return workflow


async def get_workflow(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | str,
    workflow_id: uuid.UUID | str,
) -> Optional[Workflow]:
    """Load one workflow, scoped to its owner. Returns None if absent or not owned."""
    result = await db.execute(
        select(Workflow).where(
            Workflow.id == _as_uuid(workflow_id),
            Workflow.user_id == _as_uuid(user_id),
        )
    )
    return result.scalar_one_or_none()


async def list_workflows(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | str,
) -> list[Workflow]:
    """List the caller's workflows, newest first."""
    result = await db.execute(
        select(Workflow)
        .where(Workflow.user_id == _as_uuid(user_id))
        .order_by(Workflow.created_at.desc())
    )
    return list(result.scalars().all())


async def set_n8n_workflow_id(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | str,
    workflow_id: uuid.UUID | str,
    n8n_workflow_id: str,
) -> Optional[Workflow]:
    """Record the n8n workflow identifier returned on push (FR-2). Owner-scoped."""
    workflow = await get_workflow(db, user_id=user_id, workflow_id=workflow_id)
    if workflow is None:
        return None
    workflow.n8n_workflow_id = n8n_workflow_id
    await db.flush()
    return workflow


# ============================================================================
# WorkflowExecution
# ============================================================================

async def create_execution(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | str,
    workflow_id: uuid.UUID | str,
    total_steps: int,
    trigger_type: Optional[str] = None,
    triggered_by: Optional[dict[str, Any]] = None,
    status: str = "running",
) -> WorkflowExecution:
    """Create a run record for a workflow the caller owns."""
    execution = WorkflowExecution(
        workflow_id=_as_uuid(workflow_id),
        user_id=_as_uuid(user_id),
        total_steps=total_steps,
        trigger_type=trigger_type,
        triggered_by=triggered_by,
        status=status,
    )
    db.add(execution)
    await db.flush()
    return execution


async def get_execution(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | str,
    execution_id: uuid.UUID | str,
) -> Optional[WorkflowExecution]:
    """Load one execution, scoped to its owner. Returns None if absent or not owned."""
    result = await db.execute(
        select(WorkflowExecution).where(
            WorkflowExecution.id == _as_uuid(execution_id),
            WorkflowExecution.user_id == _as_uuid(user_id),
        )
    )
    return result.scalar_one_or_none()


async def list_executions(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | str,
    workflow_id: uuid.UUID | str,
) -> list[WorkflowExecution]:
    """List a workflow's run history, newest first. Owner-scoped on both rows."""
    result = await db.execute(
        select(WorkflowExecution)
        .where(
            WorkflowExecution.workflow_id == _as_uuid(workflow_id),
            WorkflowExecution.user_id == _as_uuid(user_id),
        )
        .order_by(WorkflowExecution.created_at.desc())
    )
    return list(result.scalars().all())


async def update_execution(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | str,
    execution_id: uuid.UUID | str,
    **fields: Any,
) -> Optional[WorkflowExecution]:
    """
    Patch fields on an execution the caller owns (status, counters, timing, step_state,
    output_summary, error_message, …). Unknown attributes are ignored. Owner-scoped.
    """
    execution = await get_execution(db, user_id=user_id, execution_id=execution_id)
    if execution is None:
        return None
    for key, value in fields.items():
        if hasattr(execution, key):
            setattr(execution, key, value)
    await db.flush()
    return execution
