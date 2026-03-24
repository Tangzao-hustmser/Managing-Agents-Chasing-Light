"""审批流程路由：查看、批准、拒绝待审项。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ApprovalTask, User
from app.routers.auth import get_current_user
from app.schemas import ApprovalTaskApprove, ApprovalTaskOut
from app.services.approval_service import (
    approve_task,
    get_approval_by_id,
    get_pending_approvals,
    reject_task,
)
from app.services.auth_service import is_admin

router = APIRouter(prefix="/approvals", tags=["审批流程"])


@router.get("", response_model=list[ApprovalTaskOut])
def list_approvals(
    status: str = "pending",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """列出审批任务。
    
    参数：
    - status: pending/approved/rejected/all
    """
    if status == "pending":
        tasks = get_pending_approvals(db)
    elif status == "all":
        tasks = db.query(ApprovalTask).order_by(ApprovalTask.created_at.desc()).limit(50).all()
    else:
        tasks = db.query(ApprovalTask).filter(ApprovalTask.status == status).order_by(ApprovalTask.created_at.desc()).limit(50).all()
    
    return tasks


@router.get("/{approval_id}", response_model=ApprovalTaskOut)
def get_approval(
    approval_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取审批任务详情。"""
    task = get_approval_by_id(db, approval_id)
    if not task:
        raise HTTPException(status_code=404, detail="审批任务不存在")
    return task


@router.post("/{approval_id}/approve", response_model=ApprovalTaskOut)
def approve(
    approval_id: int,
    payload: ApprovalTaskApprove,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """批准或拒绝审批任务（仅管理员）。"""
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="仅管理员可审批")
    
    task = get_approval_by_id(db, approval_id)
    if not task:
        raise HTTPException(status_code=404, detail="审批任务不存在")
    
    if task.status != "pending":
        raise HTTPException(status_code=400, detail="该任务已处理")
    
    if payload.approved:
        task = approve_task(db, task, current_user, payload.reason)
    else:
        task = reject_task(db, task, current_user, payload.reason)
    
    return task


@router.get("/stats/summary")
def approval_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """审批统计摘要。"""
    total = db.query(func.count(ApprovalTask.id)).scalar() or 0
    pending = db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "pending").scalar() or 0
    approved = db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "approved").scalar() or 0
    rejected = db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "rejected").scalar() or 0
    
    return {
        "total": total,
        "pending": pending,
        "approved": approved,
        "rejected": rejected
    }
