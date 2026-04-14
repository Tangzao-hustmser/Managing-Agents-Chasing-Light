"""Follow-up task routes for governance closed-loop management."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import case, or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import FollowUpTask, Transaction, User
from app.routers.auth import get_current_user
from app.schemas import FollowUpTaskDetailOut, FollowUpTaskUpdate
from app.services.auth_service import is_teacher_or_admin
from app.services.audit_service import write_audit_log
from app.services.follow_up_task_service import apply_follow_up_sla, compute_sla_status
from app.services.rate_limit_service import RateLimitExceededError, enforce_write_rate_limit
from app.services.transaction_service import append_note

router = APIRouter(prefix="/follow-up-tasks", tags=["follow-up-tasks"])


def _enforce_write_limit(user_id: int, endpoint_key: str) -> None:
    try:
        enforce_write_rate_limit(user_id=user_id, endpoint_key=endpoint_key)
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc


def _can_update_task(task: FollowUpTask, current_user: User) -> bool:
    return bool(
        is_teacher_or_admin(current_user)
        or (task.assigned_user_id is not None and task.assigned_user_id == current_user.id)
    )


def _build_follow_up_out(task: FollowUpTask, current_user: User) -> dict:
    now = datetime.utcnow()
    return {
        "id": task.id,
        "transaction_id": task.transaction_id,
        "resource_id": task.resource_id,
        "resource_item_id": task.resource_item_id,
        "assigned_user_id": task.assigned_user_id,
        "task_type": task.task_type,
        "status": task.status,
        "title": task.title,
        "description": task.description or "",
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "due_at": task.due_at,
        "closed_at": task.closed_at,
        "result": task.result or "",
        "outcome_score": task.outcome_score,
        "escalation_level": int(task.escalation_level or 0),
        "escalated_at": task.escalated_at,
        "resource_name": task.resource.name if task.resource else f"Resource#{task.resource_id}",
        "resource_category": task.resource.category if task.resource else "unknown",
        "resource_item_asset_number": task.resource_item.asset_number if task.resource_item else None,
        "assigned_user_name": task.assigned_user.real_name if task.assigned_user else None,
        "transaction_action": task.transaction.action if task.transaction else None,
        "sla_status": compute_sla_status(task, now),
        "can_update": _can_update_task(task, current_user),
    }


@router.get("", response_model=list[FollowUpTaskDetailOut])
def list_follow_up_tasks(
    status: str = Query(default="open", description="open/in_progress/done/cancelled/all"),
    assigned: str = Query(default="me", description="me/all"),
    task_type: Optional[str] = Query(default=None, description="optional task type filter"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List follow-up tasks with role-based visibility."""
    apply_follow_up_sla(db)
    db.commit()

    query = db.query(FollowUpTask).options(
        joinedload(FollowUpTask.resource),
        joinedload(FollowUpTask.resource_item),
        joinedload(FollowUpTask.assigned_user),
        joinedload(FollowUpTask.transaction),
    )

    if status != "all":
        query = query.filter(FollowUpTask.status == status)
    if task_type:
        query = query.filter(FollowUpTask.task_type == task_type)

    if is_teacher_or_admin(current_user):
        if assigned == "me":
            query = query.filter(FollowUpTask.assigned_user_id == current_user.id)
        elif assigned != "all":
            raise HTTPException(status_code=400, detail="assigned must be 'me' or 'all'")
    else:
        if assigned == "all":
            raise HTTPException(status_code=403, detail="Students cannot query all follow-up tasks")
        query = query.filter(
            or_(
                FollowUpTask.assigned_user_id == current_user.id,
                FollowUpTask.transaction.has(Transaction.user_id == current_user.id),
            )
        )

    status_rank = case(
        (FollowUpTask.status == "open", 0),
        (FollowUpTask.status == "in_progress", 1),
        (FollowUpTask.status == "done", 2),
        else_=3,
    )
    rows = query.order_by(status_rank.asc(), FollowUpTask.due_at.asc(), FollowUpTask.created_at.desc()).limit(limit).all()
    return [_build_follow_up_out(task, current_user) for task in rows]


@router.patch("/{task_id}", response_model=FollowUpTaskDetailOut)
def update_follow_up_task(
    task_id: int,
    payload: FollowUpTaskUpdate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a follow-up task status and append processing notes."""
    apply_follow_up_sla(db)
    db.commit()

    task = (
        db.query(FollowUpTask)
        .options(
            joinedload(FollowUpTask.resource),
            joinedload(FollowUpTask.resource_item),
            joinedload(FollowUpTask.assigned_user),
            joinedload(FollowUpTask.transaction),
        )
        .filter(FollowUpTask.id == task_id)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Follow-up task not found")
    if not _can_update_task(task, current_user):
        raise HTTPException(status_code=403, detail="You cannot update this follow-up task")
    _enforce_write_limit(current_user.id, "follow_up_tasks.update")

    previous_status = task.status
    task.status = payload.status
    now = datetime.utcnow()
    task.updated_at = now

    note = payload.note.strip()
    if note:
        actor = current_user.real_name or current_user.username
        stamped_note = f"[{now.isoformat()}] {actor}: {note}"
        task.description = append_note(task.description, stamped_note)

    if payload.result is not None:
        task.result = payload.result.strip()
    if payload.outcome_score is not None:
        task.outcome_score = float(payload.outcome_score)

    if payload.status in {"done", "cancelled"}:
        task.closed_at = now
        if not (task.result or "").strip() and note:
            task.result = note
        if task.outcome_score is None:
            task.outcome_score = 100.0 if payload.status == "done" else 60.0
    elif previous_status in {"done", "cancelled"}:
        task.closed_at = None

    db.add(task)
    write_audit_log(
        db,
        actor=current_user,
        action="follow_up_task.update",
        entity_type="follow_up_task",
        entity_id=task.id,
        detail={
            "previous_status": previous_status,
            "next_status": payload.status,
            "outcome_score": task.outcome_score,
        },
        request=request,
    )
    db.commit()
    db.refresh(task)
    return _build_follow_up_out(task, current_user)
