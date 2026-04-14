"""Approval workflow helpers."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.models import ApprovalTask, Transaction, User
from app.services.concurrency_service import acquire_entity_lock
from app.services.notification_service import dispatch_notification_event
from app.services.transaction_service import action_requires_approval, apply_inventory_change


def should_require_approval(action: str) -> bool:
    """Return True if the action must enter the approval queue."""
    return action_requires_approval(action)


def create_approval_task(
    db: Session,
    transaction: Transaction,
    requester: User,
    reason: str = "",
) -> ApprovalTask:
    """Create a pending approval task without committing."""
    task = ApprovalTask(
        transaction_id=transaction.id,
        requester_id=requester.id,
        status="pending",
        reason=reason,
    )
    db.add(task)
    db.flush()
    resource_name = transaction.resource.name if transaction.resource else f"Resource#{transaction.resource_id}"
    dispatch_notification_event(
        db,
        event_type="approval_pending",
        title="待审批提醒",
        content=f"新增待审批申请 #{task.id}：{transaction.action} {resource_name} x{transaction.quantity}",
        correlation_key=f"approval:{task.id}",
    )
    return task


def _approval_query(db: Session):
    return db.query(ApprovalTask).options(
        joinedload(ApprovalTask.transaction).joinedload(Transaction.resource),
        joinedload(ApprovalTask.transaction).joinedload(Transaction.user),
        joinedload(ApprovalTask.requester),
        joinedload(ApprovalTask.approver),
    )


def get_pending_approvals(
    db: Session,
    limit: int = 50,
    requester_id: Optional[int] = None,
) -> List[ApprovalTask]:
    """Return pending approvals, optionally scoped to one requester."""
    query = _approval_query(db).filter(ApprovalTask.status == "pending")
    if requester_id is not None:
        query = query.filter(ApprovalTask.requester_id == requester_id)
    return query.order_by(ApprovalTask.created_at.desc()).limit(limit).all()


def approve_task(
    db: Session,
    task: ApprovalTask,
    approver: User,
    reason: str = "",
) -> ApprovalTask:
    """Approve a task and apply the inventory effect."""
    with acquire_entity_lock(f"approval:{task.id}"):
        locked_task = (
            _approval_query(db)
            .filter(ApprovalTask.id == task.id)
            .first()
        )
        if not locked_task:
            raise ValueError("Approval task not found")
        if locked_task.status != "pending":
            raise ValueError("This approval task has already been handled")
        if locked_task.requester_id == approver.id:
            raise ValueError("You cannot approve your own request")

        tx = locked_task.transaction
        if not tx:
            raise ValueError("The linked transaction does not exist")

        locked_task.status = "approved"
        locked_task.approver_id = approver.id
        locked_task.approved_at = datetime.utcnow()
        locked_task.reason = reason or locked_task.reason

        tx.status = "approved"
        tx.is_approved = True
        apply_inventory_change(db, tx)
        return locked_task


def reject_task(
    db: Session,
    task: ApprovalTask,
    approver: User,
    reason: str,
) -> ApprovalTask:
    """Reject a task without touching inventory."""
    with acquire_entity_lock(f"approval:{task.id}"):
        locked_task = (
            _approval_query(db)
            .filter(ApprovalTask.id == task.id)
            .first()
        )
        if not locked_task:
            raise ValueError("Approval task not found")
        if locked_task.status != "pending":
            raise ValueError("This approval task has already been handled")
        if locked_task.requester_id == approver.id:
            raise ValueError("You cannot approve your own request")

        tx = locked_task.transaction
        if not tx:
            raise ValueError("The linked transaction does not exist")

        locked_task.status = "rejected"
        locked_task.approver_id = approver.id
        locked_task.approved_at = datetime.utcnow()
        locked_task.reason = reason or locked_task.reason

        tx.status = "rejected"
        tx.is_approved = False
        return locked_task


def get_approval_by_id(db: Session, approval_id: int) -> Optional[ApprovalTask]:
    """Fetch one approval task with all display relations loaded."""
    return _approval_query(db).filter(ApprovalTask.id == approval_id).first()
