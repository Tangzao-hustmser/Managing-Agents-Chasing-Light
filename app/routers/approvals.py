"""Approval routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ApprovalTask, User
from app.routers.auth import get_current_user
from app.schemas import ApprovalTaskApprove, ApprovalTaskOut
from app.services.approval_service import approve_task, get_approval_by_id, get_pending_approvals, reject_task
from app.services.auth_service import is_teacher_or_admin
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve or reject one pending task."""
    if not is_teacher_or_admin(current_user):
        raise HTTPException(status_code=403, detail="Only teachers or admins can review approvals")

    task = get_approval_by_id(db, approval_id)
    if not task:
        raise HTTPException(status_code=404, detail="Approval task not found")

    try:
        if payload.approved:
            task = approve_task(db, task, current_user, payload.reason)
        else:
            task = reject_task(db, task, current_user, payload.reason)
        db.commit()
        task = get_approval_by_id(db, approval_id)
        return build_approval_out(task, current_user)
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
