"""
Founder OS — Task Review Routes
==================================
Endpoints for reviewing, approving, editing, and rejecting agent outputs.

This is the human-in-the-loop review interface — founders can:
  - List tasks pending review
  - View task details + agent output
  - Approve a task (accept output as-is)
  - Edit a task output (modify agent work before accepting)
  - Reject a task (send back for re-run or discard)
  - Provide feedback on any task

Endpoints:
    GET    /api/review/tasks            — List tasks for review
    GET    /api/review/tasks/{id}       — Get task detail with outputs
    POST   /api/review/tasks/{id}/approve   — Approve task output
    POST   /api/review/tasks/{id}/reject    — Reject task output
    POST   /api/review/tasks/{id}/edit      — Edit and approve task output
    POST   /api/review/tasks/{id}/feedback  — Submit feedback for a task
    GET    /api/review/stats            — Review queue stats
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import ClerkUser, require_auth
from app.database import get_db
from app.redis import get_redis
from app.models import Task, Output, Agent, TaskFeedback

router = APIRouter(prefix="/api/review", tags=["review"])


# ── Request / Response models ─────────────────────────────

class TaskOutputResponse(BaseModel):
    id: str
    output_type: Optional[str]
    title: Optional[str]
    content: Optional[str]
    format: Optional[str]
    word_count: Optional[int]
    version: int
    publish_status: str
    user_rating: Optional[int]
    user_feedback: Optional[str]
    created_at: str


class TaskDetailResponse(BaseModel):
    id: str
    title: str
    description: Optional[str]
    task_type: Optional[str]
    status: str
    priority: int
    agent_name: str
    agent_display_name: str
    input_data: Optional[dict]
    output_data: Optional[dict]
    outputs: list[TaskOutputResponse]
    requires_approval: bool
    approved_at: Optional[str]
    approval_notes: Optional[str]
    tokens_used: Optional[int]
    cost_usd: Optional[float]
    duration_seconds: Optional[int]
    attempts: int
    error_message: Optional[str]
    created_at: str
    completed_at: Optional[str]


class TaskListItem(BaseModel):
    id: str
    title: str
    description: Optional[str]
    task_type: Optional[str]
    status: str
    priority: int
    agent_name: str
    agent_display_name: str
    requires_approval: bool
    output_preview: Optional[str]  # First 200 chars of latest output
    created_at: str
    completed_at: Optional[str]


class TaskListResponse(BaseModel):
    tasks: list[TaskListItem]
    total: int
    has_more: bool


class ApproveRequest(BaseModel):
    notes: Optional[str] = Field(None, description="Approval notes")


class RejectRequest(BaseModel):
    reason: str = Field(..., min_length=1, description="Reason for rejection")
    retry: bool = Field(False, description="Whether to retry the task")


class EditRequest(BaseModel):
    edited_content: str = Field(..., min_length=1, description="Edited output content")
    edit_notes: Optional[str] = Field(None, description="Notes about what was changed")


class FeedbackRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Rating 1-5")
    feedback_type: Optional[str] = Field(None, description="Type: helpful, inaccurate, incomplete, off_topic")
    comments: Optional[str] = Field(None, description="Free-text comments")


class ReviewStatsResponse(BaseModel):
    pending_review: int
    approved_today: int
    rejected_today: int
    edited_today: int
    total_tasks: int
    avg_rating: Optional[float]


# ── Helpers ───────────────────────────────────────────────

def _get_user_uuid(user: ClerkUser) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"clerk:{user.user_id}")


def _format_dt(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _task_to_list_item(task: Task, agent_display: str, preview: Optional[str]) -> TaskListItem:
    return TaskListItem(
        id=str(task.id),
        title=task.title,
        description=task.description,
        task_type=task.task_type,
        status=task.status,
        priority=task.priority,
        agent_name=task.agent.name if task.agent else "unknown",
        agent_display_name=agent_display,
        requires_approval=task.requires_approval,
        output_preview=preview,
        created_at=task.created_at.isoformat(),
        completed_at=_format_dt(task.completed_at),
    )


def _task_to_detail(task: Task, agent_display: str) -> TaskDetailResponse:
    outputs = []
    for o in (task.outputs or []):
        outputs.append(TaskOutputResponse(
            id=str(o.id),
            output_type=o.output_type,
            title=o.title,
            content=o.content,
            format=o.format,
            word_count=o.word_count,
            version=o.version,
            publish_status=o.publish_status,
            user_rating=o.user_rating,
            user_feedback=o.user_feedback,
            created_at=o.created_at.isoformat(),
        ))

    return TaskDetailResponse(
        id=str(task.id),
        title=task.title,
        description=task.description,
        task_type=task.task_type,
        status=task.status,
        priority=task.priority,
        agent_name=task.agent.name if task.agent else "unknown",
        agent_display_name=agent_display,
        input_data=task.input_data,
        output_data=task.output_data,
        outputs=outputs,
        requires_approval=task.requires_approval,
        approved_at=_format_dt(task.approved_at),
        approval_notes=task.approval_notes,
        tokens_used=task.tokens_used,
        cost_usd=float(task.cost_usd) if task.cost_usd else None,
        duration_seconds=task.duration_seconds,
        attempts=task.attempts,
        error_message=task.error_message,
        created_at=task.created_at.isoformat(),
        completed_at=_format_dt(task.completed_at),
    )


# ── Routes ────────────────────────────────────────────────

@router.get("/tasks", response_model=TaskListResponse)
async def list_review_tasks(
    status: Optional[str] = Query(
        default=None,
        description="Filter by status: pending, completed, approved, rejected, failed",
    ),
    agent: Optional[str] = Query(default=None, description="Filter by agent name"),
    needs_review: bool = Query(default=False, description="Only show tasks needing approval"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """List tasks available for review."""
    user_uuid = _get_user_uuid(user)

    query = (
        select(Task)
        .options(selectinload(Task.agent), selectinload(Task.outputs))
        .where(Task.user_id == user_uuid)
        .order_by(desc(Task.created_at))
    )

    if status:
        query = query.where(Task.status == status)
    
    if needs_review:
        query = query.where(
            and_(
                Task.requires_approval == True,
                Task.approved_at.is_(None),
                Task.status.in_(["completed", "pending_review"]),
            )
        )

    if agent:
        query = query.join(Agent).where(Agent.name == agent)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    result = await db.execute(query.offset(offset).limit(limit))
    tasks = result.scalars().all()

    items = []
    for task in tasks:
        display = task.agent.display_name if task.agent else "Unknown"
        preview = None
        if task.outputs:
            latest = sorted(task.outputs, key=lambda o: o.version, reverse=True)[0]
            if latest.content:
                preview = latest.content[:200]
        elif task.output_data:
            content = task.output_data.get("content", "")
            preview = content[:200] if content else None

        items.append(_task_to_list_item(task, display, preview))

    return TaskListResponse(
        tasks=items,
        total=total,
        has_more=(offset + limit) < total,
    )


@router.get("/tasks/{task_id}", response_model=TaskDetailResponse)
async def get_task_detail(
    task_id: str,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed task info with all outputs."""
    user_uuid = _get_user_uuid(user)

    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID")

    result = await db.execute(
        select(Task)
        .options(selectinload(Task.agent), selectinload(Task.outputs))
        .where(and_(Task.id == tid, Task.user_id == user_uuid))
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    display = task.agent.display_name if task.agent else "Unknown"
    return _task_to_detail(task, display)


@router.post("/tasks/{task_id}/approve")
async def approve_task(
    task_id: str,
    body: ApproveRequest = ApproveRequest(),
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Approve a task output — accept as-is."""
    user_uuid = _get_user_uuid(user)

    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID")

    result = await db.execute(
        select(Task)
        .options(selectinload(Task.agent))
        .where(and_(Task.id == tid, Task.user_id == user_uuid))
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status not in ("completed", "pending_review", "pending"):
        raise HTTPException(status_code=409, detail=f"Task status is '{task.status}', cannot approve")

    task.status = "approved"
    task.approved_by = user_uuid
    task.approved_at = datetime.now(timezone.utc)
    task.approval_notes = body.notes or "Approved"

    await db.commit()

    return {
        "id": str(task.id),
        "status": "approved",
        "message": "Task approved successfully",
    }


@router.post("/tasks/{task_id}/reject")
async def reject_task(
    task_id: str,
    body: RejectRequest,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Reject a task output — optionally retry."""
    user_uuid = _get_user_uuid(user)

    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID")

    result = await db.execute(
        select(Task)
        .options(selectinload(Task.agent))
        .where(and_(Task.id == tid, Task.user_id == user_uuid))
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = "rejected"
    task.approval_notes = f"Rejected: {body.reason}"

    if body.retry and task.attempts < task.max_attempts:
        task.status = "pending"
        task.attempts += 1
        task.error_message = f"Rejected (attempt {task.attempts}): {body.reason}"

    await db.commit()

    return {
        "id": str(task.id),
        "status": task.status,
        "message": "Task rejected" + (" and queued for retry" if body.retry else ""),
    }


@router.post("/tasks/{task_id}/edit")
async def edit_task_output(
    task_id: str,
    body: EditRequest,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """
    Edit a task's output content, then approve it.
    Creates a new version of the output with the edited content.
    """
    user_uuid = _get_user_uuid(user)

    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID")

    result = await db.execute(
        select(Task)
        .options(selectinload(Task.agent), selectinload(Task.outputs))
        .where(and_(Task.id == tid, Task.user_id == user_uuid))
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Create a new output version with the edited content
    latest_version = max((o.version for o in task.outputs), default=0)
    parent_id = task.outputs[-1].id if task.outputs else None

    new_output = Output(
        task_id=task.id,
        user_id=user_uuid,
        output_type="edited",
        title=f"{task.title} (edited)",
        content=body.edited_content,
        format="text",
        word_count=len(body.edited_content.split()),
        publish_status="draft",
        version=latest_version + 1,
        parent_output_id=parent_id,
        user_feedback=body.edit_notes,
    )
    db.add(new_output)

    # Also update task's output_data
    task.output_data = {
        **(task.output_data or {}),
        "content": body.edited_content,
        "edited": True,
        "edit_notes": body.edit_notes,
    }

    # Approve the task
    task.status = "approved"
    task.approved_by = user_uuid
    task.approved_at = datetime.now(timezone.utc)
    task.approval_notes = f"Edited and approved: {body.edit_notes or 'No notes'}"

    await db.commit()

    return {
        "id": str(task.id),
        "status": "approved",
        "output_version": latest_version + 1,
        "message": "Task output edited and approved",
    }


@router.post("/tasks/{task_id}/feedback")
async def submit_task_feedback(
    task_id: str,
    body: FeedbackRequest,
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Submit feedback for a task (rating + comments)."""
    user_uuid = _get_user_uuid(user)

    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID")

    result = await db.execute(
        select(Task).where(and_(Task.id == tid, Task.user_id == user_uuid))
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    feedback = TaskFeedback(
        task_id=task.id,
        user_id=user_uuid,
        rating=body.rating,
        feedback_type=body.feedback_type,
        comments=body.comments,
        action_taken="feedback",
    )
    db.add(feedback)
    await db.commit()

    return {
        "id": str(feedback.id),
        "task_id": str(task.id),
        "rating": body.rating,
        "message": "Feedback submitted",
    }


# ── Review Stats ──────────────────────────────────────────

@router.get("/stats", response_model=ReviewStatsResponse)
async def get_review_stats(
    user: ClerkUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get review queue stats."""
    user_uuid = _get_user_uuid(user)
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # Pending review count
    pending_q = await db.execute(
        select(func.count(Task.id)).where(
            and_(
                Task.user_id == user_uuid,
                Task.requires_approval == True,
                Task.approved_at.is_(None),
                Task.status.in_(["completed", "pending_review"]),
            )
        )
    )
    pending_review = pending_q.scalar() or 0

    # Approved today
    approved_q = await db.execute(
        select(func.count(Task.id)).where(
            and_(
                Task.user_id == user_uuid,
                Task.status == "approved",
                Task.approved_at >= today_start,
            )
        )
    )
    approved_today = approved_q.scalar() or 0

    # Rejected today
    rejected_q = await db.execute(
        select(func.count(Task.id)).where(
            and_(
                Task.user_id == user_uuid,
                Task.status == "rejected",
                Task.created_at >= today_start,
            )
        )
    )
    rejected_today = rejected_q.scalar() or 0

    # Edited (outputs with type=edited) today
    edited_q = await db.execute(
        select(func.count(Output.id)).where(
            and_(
                Output.user_id == user_uuid,
                Output.output_type == "edited",
                Output.created_at >= today_start,
            )
        )
    )
    edited_today = edited_q.scalar() or 0

    # Total tasks
    total_q = await db.execute(
        select(func.count(Task.id)).where(Task.user_id == user_uuid)
    )
    total_tasks = total_q.scalar() or 0

    # Avg rating
    avg_q = await db.execute(
        select(func.avg(TaskFeedback.rating)).where(TaskFeedback.user_id == user_uuid)
    )
    avg_rating = avg_q.scalar()
    avg_rating = round(float(avg_rating), 2) if avg_rating else None

    return ReviewStatsResponse(
        pending_review=pending_review,
        approved_today=approved_today,
        rejected_today=rejected_today,
        edited_today=edited_today,
        total_tasks=total_tasks,
        avg_rating=avg_rating,
    )
