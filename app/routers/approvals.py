"""Approval routes."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ApprovalTask, User
from app.routers.auth import get_current_user
from app.schemas import ApprovalTaskApprove, ApprovalTaskOut
from app.services.approval_service import approve_task, get_approval_by_id, get_pending_approvals, reject_task
from app.services.auth_service import is_teacher_or_admin
from app.services.concurrency_service import acquire_entity_lock
from app.services.audit_service import write_audit_log
from app.services.idempotency_service import (
    IdempotencyConflictError,
    persist_idempotent_response,
    prepare_idempotency,
)
from app.services.rate_limit_service import RateLimitExceededError, enforce_write_rate_limit
from app.services.transaction_service import build_approval_out

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalTaskOut])
def list_approvals(
    status: str = "pending",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List approvals for staff or the current user's own requests."""
    if is_teacher_or_admin(current_user):
        if status == "pending":
            tasks = get_pending_approvals(db)
        elif status == "all":
            tasks = (
                db.query(ApprovalTask)
                .order_by(ApprovalTask.created_at.desc())
                .limit(50)
                .all()
            )
            tasks = [get_approval_by_id(db, task.id) for task in tasks]
        else:
            tasks = (
                db.query(ApprovalTask)
                .filter(ApprovalTask.status == status)
                .order_by(ApprovalTask.created_at.desc())
                .limit(50)
                .all()
            )
            tasks = [get_approval_by_id(db, task.id) for task in tasks]
    else:
        if status == "all":
            tasks = get_pending_approvals(db, requester_id=current_user.id, limit=50)
            extra = (
                db.query(ApprovalTask.id)
                .filter(
                    ApprovalTask.requester_id == current_user.id,
                    ApprovalTask.status.in_(["approved", "rejected"]),
                )
                .order_by(ApprovalTask.created_at.desc())
                .limit(50)
                .all()
            )
            tasks_by_id = {task.id: task for task in tasks}
            for task_id, in extra:
                full_task = get_approval_by_id(db, task_id)
                if full_task:
                    tasks_by_id[full_task.id] = full_task
            tasks = list(tasks_by_id.values())
            tasks.sort(key=lambda item: item.created_at, reverse=True)
        else:
            if status == "pending":
                tasks = get_pending_approvals(db, requester_id=current_user.id, limit=50)
            else:
                rows = (
                    db.query(ApprovalTask.id)
                    .filter(
                        ApprovalTask.requester_id == current_user.id,
                        ApprovalTask.status == status,
                    )
                    .order_by(ApprovalTask.created_at.desc())
                    .limit(50)
                    .all()
                )
                tasks = [get_approval_by_id(db, approval_id) for approval_id, in rows]
                tasks = [task for task in tasks if task]

    return [build_approval_out(task, current_user) for task in tasks]


@router.get("/{approval_id}", response_model=ApprovalTaskOut)
def get_approval(
    approval_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get one approval task."""
    task = get_approval_by_id(db, approval_id)
    if not task:
        raise HTTPException(status_code=404, detail="Approval task not found")
    if not is_teacher_or_admin(current_user) and task.requester_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only view your own approval status")
    return build_approval_out(task, current_user)


@router.post("/{approval_id}/approve", response_model=ApprovalTaskOut)
def approve(
    approval_id: int,
    payload: ApprovalTaskApprove,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve or reject one pending task."""
    if not is_teacher_or_admin(current_user):
        raise HTTPException(status_code=403, detail="Only teachers or admins can review approvals")

    try:
        enforce_write_rate_limit(user_id=current_user.id, endpoint_key="approvals.review")
        with acquire_entity_lock(f"approval:{approval_id}"):
            idempotency = prepare_idempotency(
                db,
                scope="approvals.review",
                user_id=current_user.id,
                idempotency_key=idempotency_key,
                request_payload={
                    "approval_id": approval_id,
                    "approved": payload.approved,
                    "reason": payload.reason,
                },
                entity_key=f"approval:{approval_id}",
            )
            if idempotency.cached_response is not None:
                return idempotency.cached_response

            task = get_approval_by_id(db, approval_id)
            if not task:
                raise HTTPException(status_code=404, detail="Approval task not found")

            if payload.approved:
                task = approve_task(db, task, current_user, payload.reason)
                action = "approval.approve"
            else:
                task = reject_task(db, task, current_user, payload.reason)
                action = "approval.reject"

            task = get_approval_by_id(db, approval_id)
            response_payload = build_approval_out(task, current_user)
            write_audit_log(
                db,
                actor=current_user,
                action=action,
                entity_type="approval_task",
                entity_id=task.id if task else approval_id,
                detail={
                    "approved": bool(payload.approved),
                    "reason": payload.reason,
                    "status": task.status if task else "",
                    "transaction_id": task.transaction_id if task else None,
                },
                request=request,
                idempotency_key=idempotency_key or "",
            )
            persist_idempotent_response(db, context=idempotency, response_payload=response_payload, status_code=200)
            db.commit()
            return response_payload
    except HTTPException:
        db.rollback()
        raise
    except IdempotencyConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RateLimitExceededError as exc:
        db.rollback()
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to process approval: {exc}") from exc


@router.get("/stats/summary")
def approval_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return approval summary counts for staff dashboards."""
    if not is_teacher_or_admin(current_user):
        raise HTTPException(status_code=403, detail="Only teachers or admins can view approval summary")

    total = db.query(func.count(ApprovalTask.id)).scalar() or 0
    pending = db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "pending").scalar() or 0
    approved = db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "approved").scalar() or 0
    rejected = db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "rejected").scalar() or 0

    return {
        "total": total,
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
    }
