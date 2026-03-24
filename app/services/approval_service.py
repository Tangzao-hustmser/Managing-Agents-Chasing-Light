"""审批流程服务：高风险操作的审批管理。"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import ApprovalTask, Resource, Transaction, User


def should_require_approval(action: str, quantity: int, resource: Resource) -> tuple[bool, str]:
    """
    判断是否需要审批。
    
    返回 (需要审批: bool, 原因: str)
    """
    if action == "lost":
        return True, f"设备丢失，数量 {quantity}"
    
    if action == "consume" and quantity >= 10:
        return True, f"大额消耗，数量 {quantity}"
    
    if action == "replenish":
        return True, f"补货操作，数量 {quantity}"
    
    return False, ""


def create_approval_task(
    db: Session,
    transaction: Transaction,
    requester: User,
    reason: str
) -> ApprovalTask:
    """创建审批任务。"""
    task = ApprovalTask(
        transaction_id=transaction.id,
        requester_id=requester.id,
        status="pending",
        reason=reason
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_pending_approvals(db: Session, limit: int = 50) -> list[ApprovalTask]:
    """获取待审批任务。"""
    return db.query(ApprovalTask).filter(
        ApprovalTask.status == "pending"
    ).order_by(ApprovalTask.created_at.desc()).limit(limit).all()


def approve_task(
    db: Session,
    task: ApprovalTask,
    approver: User,
    reason: str = ""
) -> ApprovalTask:
    """批准审批任务。"""
    task.status = "approved"
    task.approver_id = approver.id
    task.approved_at = datetime.utcnow()
    task.reason = reason
    
    # 关联的 transaction 标记为已批准
    tx = db.query(Transaction).filter(Transaction.id == task.transaction_id).first()
    if tx:
        tx.is_approved = True
    
    db.commit()
    db.refresh(task)
    return task


def reject_task(
    db: Session,
    task: ApprovalTask,
    approver: User,
    reason: str
) -> ApprovalTask:
    """拒绝审批任务。"""
    task.status = "rejected"
    task.approver_id = approver.id
    task.approved_at = datetime.utcnow()
    task.reason = reason
    
    # 关联的 transaction 保持未批准状态，但删除库存扣减（如果有）
    # 这里暂时不删除，由前端逻辑处理
    
    db.commit()
    db.refresh(task)
    return task


def get_approval_by_id(db: Session, approval_id: int) -> ApprovalTask:
    """根据 ID 获取审批任务。"""
    return db.query(ApprovalTask).filter(ApprovalTask.id == approval_id).first()
