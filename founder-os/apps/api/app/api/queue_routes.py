"""
Founder OS — Queue API Routes
=================================
Async agent execution endpoints — submit tasks to the Celery queue
and poll for results. These are the async counterparts to the
synchronous routes in agent_routes.py.

Routes:
    POST   /api/queue/agents/{name}/run   — Submit agent run (returns task_id)
    POST   /api/queue/orchestrate         — Submit orchestration (returns task_id)
    GET    /api/queue/tasks/{task_id}      — Poll task status + result
    GET    /api/queue/tasks                — List user's recent tasks
    POST   /api/queue/tasks/{task_id}/cancel — Cancel a task
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import ClerkUser, require_auth
from app.redis import get_redis
from app.tasks.agent_tasks import run_agent_task, run_orchestration_task
from app.tasks.status import TaskStatusService

router = APIRouter(prefix="/api/queue", tags=["queue"])


# ── Request / Response models ─────────────────────────────────

class QueueRunRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000, description="User message for the agent")
    session_id: Optional[str] = Field(None, description="Optional session ID for memory scoping")
    extra_context: Optional[str] = Field(None, description="Additional context to inject into system prompt")


class TaskSubmittedResponse(BaseModel):
    """Returned immediately when a task is submitted."""
    task_id: str
    status: str = "pending"
    message: str = "Task submitted successfully"
    poll_url: str = Field(..., description="URL to poll for task status")


class TaskStatusResponse(BaseModel):
    """Full task status with result (if completed)."""
    task_id: str
    status: str  # pending | started | completed | failed | retrying | cancelled
    agent_name: Optional[str] = None
    task_type: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    failed_at: Optional[float] = None
    cancelled_at: Optional[float] = None


class TaskListResponse(BaseModel):
    tasks: list[dict]
    total: int
    limit: int
    offset: int


class TaskCancelResponse(BaseModel):
    task_id: str
    status: str = "cancelled"
    message: str = "Task cancellation requested"


# ── Routes ────────────────────────────────────────────────────

@router.post(
    "/agents/{agent_name}/run",
    response_model=TaskSubmittedResponse,
    status_code=202,
)
async def submit_agent_run(
    agent_name: str,
    body: QueueRunRequest,
    user: ClerkUser = Depends(require_auth),
):
    """
    Submit an agent run to the background queue.

    Returns immediately with a task_id. Use GET /api/queue/tasks/{task_id}
    to poll for completion.

    This is the async version of POST /api/agents/{name}/run.
    """
    result = run_agent_task.delay(
        agent_name=agent_name,
        user_id=user.user_id,
        message=body.message,
        session_id=body.session_id,
        extra_context=body.extra_context,
    )

    return TaskSubmittedResponse(
        task_id=result.id,
        status="pending",
        message=f"Agent '{agent_name}' task submitted",
        poll_url=f"/api/queue/tasks/{result.id}",
    )


@router.post(
    "/orchestrate",
    response_model=TaskSubmittedResponse,
    status_code=202,
)
async def submit_orchestration(
    body: QueueRunRequest,
    user: ClerkUser = Depends(require_auth),
):
    """
    Submit an orchestration to the background queue.

    The orchestrator analyses your request, delegates to specialist agents,
    and synthesises a response — all running in the background.

    This is the async version of POST /api/agents/orchestrate.
    """
    result = run_orchestration_task.delay(
        user_id=user.user_id,
        message=body.message,
        session_id=body.session_id,
        extra_context=body.extra_context,
    )

    return TaskSubmittedResponse(
        task_id=result.id,
        status="pending",
        message="Orchestration task submitted",
        poll_url=f"/api/queue/tasks/{result.id}",
    )


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    user: ClerkUser = Depends(require_auth),
):
    """
    Poll the status of a background task.

    Status lifecycle:
        pending → started → completed | failed | retrying | cancelled

    When status is "completed", the result field contains the full
    agent response (same shape as AgentRunResponse / OrchestrationResponse).
    """
    redis = get_redis()
    service = TaskStatusService(redis)
    status = await service.get_status(task_id)

    if status is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    return TaskStatusResponse(**status)


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    limit: int = 20,
    offset: int = 0,
    user: ClerkUser = Depends(require_auth),
):
    """
    List the authenticated user's recent background tasks.

    Ordered by submission time (most recent first).
    """
    if limit > 100:
        limit = 100

    redis = get_redis()
    service = TaskStatusService(redis)

    tasks = await service.list_user_tasks(user.user_id, limit=limit, offset=offset)
    total = await service.get_task_count(user.user_id)

    return TaskListResponse(
        tasks=tasks,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/tasks/{task_id}/cancel", response_model=TaskCancelResponse)
async def cancel_task(
    task_id: str,
    user: ClerkUser = Depends(require_auth),
):
    """
    Cancel a pending or running background task.

    If the task is already running, a SIGTERM signal will be sent to the
    worker process. The task will be marked as cancelled.
    """
    redis = get_redis()
    service = TaskStatusService(redis)

    # Verify task exists
    status = await service.get_status(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    if status.get("status") in ("completed", "failed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"Task is already {status['status']} and cannot be cancelled",
        )

    result = await service.cancel_task(task_id)

    return TaskCancelResponse(
        task_id=task_id,
        status="cancelled",
        message="Task cancellation requested",
    )
