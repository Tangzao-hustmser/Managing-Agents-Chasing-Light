"""Approval workflow helpers."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from app.models import ApprovalTask, Transaction, User
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
    if task.status != "pending":
        raise ValueError("This approval task has already been handled")
    if task.requester_id == approver.id:
        raise ValueError("You cannot approve your own request")

    tx = task.transaction
    if not tx:
        raise ValueError("The linked transaction does not exist")

    task.status = "approved"
    task.approver_id = approver.id
    task.approved_at = datetime.utcnow()
    task.reason = reason or task.reason

    tx.status = "approved"
    tx.is_approved = True
    apply_inventory_change(db, tx)
    return task


def reject_task(
    db: Session,
    task: ApprovalTask,
    approver: User,
    reason: str,
) -> ApprovalTask:
    """Reject a task without touching inventory."""
    if task.status != "pending":
        raise ValueError("This approval task has already been handled")
    if task.requester_id == approver.id:
        raise ValueError("You cannot approve your own request")

    tx = task.transaction
    if not tx:
        raise ValueError("The linked transaction does not exist")

    task.status = "rejected"
    task.approver_id = approver.id
    task.approved_at = datetime.utcnow()
    task.reason = reason or task.reason

    tx.status = "rejected"
    tx.is_approved = False
    return task


def get_approval_by_id(db: Session, approval_id: int) -> Optional[ApprovalTask]:
    """Fetch one approval task with all display relations loaded."""
    return _approval_query(db).filter(ApprovalTask.id == approval_id).first()
