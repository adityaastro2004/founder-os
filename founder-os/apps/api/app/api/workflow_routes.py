"""
Founder OS — Workflow API Routes (ADR-008 / Track G).

Exposes the user-scoped workflow + run endpoints the dashboard consumes. The
persistence is delegated to `app.workflows.service`; this layer only does
auth → user resolution → serialization into the documented API surface.

Routes (all under /api/workflows, all require auth, all owner-scoped):
    GET  /api/workflows                 — list the caller's workflows
    GET  /api/workflows/{id}            — one workflow + its IR steps
    GET  /api/workflows/{id}/runs       — that workflow's run history
    GET  /api/workflows/runs/{run_id}   — a single run (for polling)
    POST /api/workflows/{id}/run        — trigger a manual ("run now") execution
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ClerkUser, require_auth
from app.database import get_db
from app.models import Workflow, WorkflowExecution
from app.users import get_or_create_user_id
from app.workflows import service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


async def _user_uuid(user: ClerkUser, db: AsyncSession) -> uuid.UUID:
    """Resolve the internal users.id UUID (creating the row if needed)."""
    return await get_or_create_user_id(user.user_id, db, email=user.email)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _serialize_workflow(wf: Workflow) -> dict[str, Any]:
    """Shape a Workflow into the dashboard's `Workflow` contract."""
    return {
        "id": str(wf.id),
        "name": wf.name,
        "description": wf.description,
        "is_active": wf.is_active,
        "is_scheduled": wf.is_scheduled,
        "schedule_cron": wf.schedule_cron,
        "last_run_at": _iso(wf.last_run_at),
        "total_runs": wf.total_runs,
        "successful_runs": wf.successful_runs,
        "n8n_workflow_id": wf.n8n_workflow_id,
    }


def _serialize_run(run: WorkflowExecution) -> dict[str, Any]:
    """Shape a WorkflowExecution into the dashboard's `WorkflowRun` contract."""
    return {
        "id": str(run.id),
        "status": run.status,
        "trigger_type": run.trigger_type,
        "started_at": _iso(run.started_at),
        "completed_at": _iso(run.completed_at),
        "steps_completed": run.steps_completed,
        "steps_failed": run.steps_failed,
        "output_summary": run.output_summary,
        "error_message": run.error_message,
    }


def _step_count(steps: Any) -> int:
    """Number of steps in the stored IR envelope ({..., 'steps': [...]})."""
    if isinstance(steps, dict):
        inner = steps.get("steps")
        if isinstance(inner, list):
            return len(inner)
    return 0


@router.get("")
@router.get("/")
async def list_workflows(
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List the caller's workflows, newest first."""
    user_id = await _user_uuid(user, db)
    workflows = await service.list_workflows(db, user_id=user_id)
    return [_serialize_workflow(wf) for wf in workflows]


@router.get("/runs/{run_id}")
async def get_run(
    run_id: uuid.UUID,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Fetch a single run (used by the detail page to poll live status)."""
    user_id = await _user_uuid(user, db)
    run = await service.get_execution(db, user_id=user_id, execution_id=run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _serialize_run(run)


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: uuid.UUID,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """One workflow plus its IR steps envelope (the `WorkflowDetail` contract)."""
    user_id = await _user_uuid(user, db)
    wf = await service.get_workflow(db, user_id=user_id, workflow_id=workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    detail = _serialize_workflow(wf)
    detail["steps"] = wf.steps if isinstance(wf.steps, dict) else None
    return detail


@router.get("/{workflow_id}/runs")
async def list_runs(
    workflow_id: uuid.UUID,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Run history for a workflow the caller owns, newest first."""
    user_id = await _user_uuid(user, db)
    wf = await service.get_workflow(db, user_id=user_id, workflow_id=workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    runs = await service.list_executions(db, user_id=user_id, workflow_id=workflow_id)
    return [_serialize_run(run) for run in runs]


@router.post("/{workflow_id}/run")
async def run_workflow(
    workflow_id: uuid.UUID,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Trigger a manual run. Records a run row immediately so it appears in history,
    then best-effort triggers the workflow in n8n when it has been deployed
    (`n8n_workflow_id` set). If n8n is unreachable, the run is marked failed with
    a clear message rather than surfacing a 500.
    """
    user_id = await _user_uuid(user, db)
    wf = await service.get_workflow(db, user_id=user_id, workflow_id=workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    run = await service.create_execution(
        db,
        user_id=user_id,
        workflow_id=workflow_id,
        total_steps=_step_count(wf.steps),
        trigger_type="manual",
        triggered_by={"source": "dashboard", "clerk_user_id": user.user_id},
        status="running",
    )
    run.started_at = datetime.now(timezone.utc)
    wf.total_runs = (wf.total_runs or 0) + 1
    wf.last_run_at = run.started_at

    # Best-effort hand-off to n8n when the workflow has been compiled + pushed.
    if wf.n8n_workflow_id:
        from app.workflows.n8n_client import N8nClient, N8nError

        try:
            async with N8nClient.from_settings() as client:
                await client.trigger_workflow(
                    wf.n8n_workflow_id,
                    payload={"workflow_execution_id": str(run.id)},
                )
        except N8nError as exc:
            run.status = "failed"
            run.error_message = str(exc)
            run.completed_at = datetime.now(timezone.utc)
            logger.warning("n8n trigger failed for workflow %s: %s", workflow_id, exc)

    await db.flush()
    return _serialize_run(run)
