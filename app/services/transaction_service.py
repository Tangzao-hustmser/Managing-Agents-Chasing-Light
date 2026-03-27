"""Transaction policy, serialization, and inventory mutation helpers."""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Alert, ApprovalTask, Resource, Transaction, User
from app.services.auth_service import is_teacher_or_admin
from app.services.rules_engine import run_inventory_rules, run_utilization_rules, run_waste_rules
from app.services.time_slot_service import calculate_duration

APPLICATION_ACTIONS = {"borrow", "consume"}
DIRECT_ACTIONS = {"replenish", "lost", "adjust"}


def action_requires_approval(action: str) -> bool:
    """Return True when the action should enter the approval queue."""
    return action in APPLICATION_ACTIONS


def append_note(existing_note: str, extra_note: str) -> str:
    """Append a note segment without losing the original note."""
    parts = [part.strip() for part in [existing_note, extra_note] if part and part.strip()]
    return "\n".join(parts)


def get_approval_status(tx: Transaction) -> str:
    """Return the approval status shown to the front-end."""
    if tx.approval_task:
        return tx.approval_task.status
    if action_requires_approval(tx.action):
        if tx.status == "rejected":
            return "rejected"
        if tx.status in {"approved", "returned"}:
            return "approved"
        return "pending"
    return "not_required"


def can_return_transaction(tx: Transaction, current_user: Optional[User]) -> bool:
    """Whether the current user can return this transaction."""
    return bool(
        current_user
        and tx.user_id == current_user.id
        and tx.action == "borrow"
        and tx.status == "approved"
        and tx.return_time is None
    )


def build_transaction_out(tx: Transaction, current_user: Optional[User] = None) -> dict:
    """Serialize a transaction into a stable DTO."""
    resource = tx.resource
    requester = tx.user
    approval = tx.approval_task
    return {
        "id": tx.id,
        "resource_id": tx.resource_id,
        "resource_name": resource.name if resource else f"Resource#{tx.resource_id}",
        "resource_category": resource.category if resource else "unknown",
        "user_id": tx.user_id,
        "requester_name": requester.real_name if requester else f"User#{tx.user_id}",
        "requester_role": requester.role if requester else "unknown",
        "action": tx.action,
        "quantity": tx.quantity,
        "note": tx.note or "",
        "purpose": tx.purpose or "",
        "status": tx.status,
        "approval_status": get_approval_status(tx),
        "approval_id": approval.id if approval else None,
        "borrow_time": tx.borrow_time,
        "expected_return_time": tx.expected_return_time,
        "return_time": tx.return_time,
        "duration_minutes": tx.duration_minutes,
        "condition_return": tx.condition_return or "good",
        "can_return": can_return_transaction(tx, current_user),
        "inventory_applied": bool(tx.inventory_applied),
        "inventory_before_total": tx.inventory_before_total,
        "inventory_after_total": tx.inventory_after_total,
        "inventory_before_available": tx.inventory_before_available,
        "inventory_after_available": tx.inventory_after_available,
        "return_inventory_before_available": tx.return_inventory_before_available,
        "return_inventory_after_available": tx.return_inventory_after_available,
        "created_at": tx.created_at,
    }


def build_approval_suggestion(task: ApprovalTask) -> str:
    """Generate a simple rule-based suggestion for demo purposes."""
    tx = task.transaction
    resource = tx.resource if tx else None
    if not tx or not resource:
        return "Please review manually: incomplete transaction context."

    if tx.action == "borrow" and resource.category != "device":
        return "Suggest reject: borrowing is only valid for device resources."
    if tx.action == "consume" and resource.category != "material":
        return "Suggest reject: consumption is only valid for material resources."
    if tx.quantity > resource.available_count:
        return "Suggest reject: current available inventory is not enough."
    if tx.action == "consume" and tx.quantity >= max(resource.min_threshold, 1) * 2:
        return "Suggest manual review: quantity is much higher than the low-stock threshold."
    return "Suggest approve: the request matches the current inventory policy."


def build_approval_out(task: ApprovalTask, current_user: Optional[User] = None) -> dict:
    """Serialize an approval task into a stable DTO."""
    tx = task.transaction
    resource = tx.resource if tx and tx.resource else None
    requester = task.requester
    approver = task.approver
    return {
        "id": task.id,
        "transaction_id": task.transaction_id,
        "requester_id": task.requester_id,
        "requester_name": requester.real_name if requester else f"User#{task.requester_id}",
        "requester_role": requester.role if requester else "unknown",
        "approver_id": task.approver_id,
        "approver_name": approver.real_name if approver else None,
        "resource_id": tx.resource_id if tx else 0,
        "resource_name": resource.name if resource else "Unknown resource",
        "resource_category": resource.category if resource else "unknown",
        "action": tx.action if tx else "unknown",
        "quantity": tx.quantity if tx else 0,
        "note": tx.note if tx else "",
        "purpose": tx.purpose if tx else "",
        "status": task.status,
        "reason": task.reason or "",
        "created_at": task.created_at,
        "approved_at": task.approved_at,
        "can_approve": bool(
            current_user
            and is_teacher_or_admin(current_user)
            and task.status == "pending"
            and current_user.id != task.requester_id
        ),
        "suggestion": build_approval_suggestion(task),
    }


def validate_resource_action(resource: Resource, action: str) -> None:
    """Validate category/action pairing."""
    if action == "borrow" and resource.category != "device":
        raise ValueError("Borrow requests are only allowed for device resources")
    if action == "consume" and resource.category != "material":
        raise ValueError("Consume requests are only allowed for material resources")


def apply_inventory_change(db: Session, tx: Transaction) -> Transaction:
    """Apply the inventory effect for one transaction exactly once."""
    if tx.inventory_applied:
        raise ValueError("Inventory change has already been applied")
    if not tx.resource:
        raise ValueError("Transaction resource is missing")

    resource = tx.resource
    before_total = resource.total_count
    before_available = resource.available_count

    if tx.action in {"borrow", "consume"}:
        if tx.quantity > resource.available_count:
            raise ValueError("Insufficient available inventory")
        resource.available_count -= tx.quantity
    elif tx.action == "replenish":
        resource.total_count += tx.quantity
        resource.available_count += tx.quantity
    elif tx.action == "lost":
        if tx.quantity > resource.total_count:
            raise ValueError("Lost quantity exceeds total inventory")
        resource.total_count -= tx.quantity
        resource.available_count = max(0, resource.available_count - tx.quantity)
    elif tx.action == "adjust":
        if tx.inventory_after_total is None or tx.inventory_after_available is None:
            raise ValueError("Adjustment targets are missing")
        if tx.inventory_after_available > tx.inventory_after_total:
            raise ValueError("Available inventory cannot exceed total inventory")
        resource.total_count = tx.inventory_after_total
        resource.available_count = tx.inventory_after_available
    else:
        raise ValueError("Unsupported inventory action")

    tx.inventory_before_total = before_total
    tx.inventory_after_total = resource.total_count
    tx.inventory_before_available = before_available
    tx.inventory_after_available = resource.available_count
    tx.inventory_applied = True
    tx.is_approved = True
    if tx.status == "pending":
        tx.status = "approved"

    run_inventory_rules(db, resource)
    run_utilization_rules(db, resource)
    if tx.action in {"consume", "lost"}:
        run_waste_rules(db, resource, tx.action, tx.quantity)
    return tx


def apply_return(db: Session, tx: Transaction, condition_return: str, note: str = "") -> Transaction:
    """Close an approved borrow record and restore availability."""
    if tx.action != "borrow":
        raise ValueError("Only borrow records can be returned")
    if tx.status != "approved":
        raise ValueError("Only approved borrow records can be returned")
    if tx.return_time is not None:
        raise ValueError("This borrow record has already been returned")
    if not tx.resource:
        raise ValueError("Transaction resource is missing")

    resource = tx.resource
    before_available = resource.available_count
    resource.available_count = min(resource.total_count, resource.available_count + tx.quantity)

    tx.return_time = datetime.utcnow()
    tx.condition_return = condition_return
    tx.duration_minutes = calculate_duration(tx.borrow_time, tx.return_time) if tx.borrow_time else None
    tx.return_inventory_before_available = before_available
    tx.return_inventory_after_available = resource.available_count
    tx.status = "returned"
    if note:
        tx.note = append_note(tx.note, f"Return note: {note}")

    run_inventory_rules(db, resource)
    run_utilization_rules(db, resource)

    if condition_return != "good":
        level = "warn" if condition_return == "damaged" else "error"
        db.add(
            Alert(
                level=level,
                type="return_exception",
                message=f"Resource [{resource.name}] was returned with condition={condition_return}.",
            )
        )

    return tx
