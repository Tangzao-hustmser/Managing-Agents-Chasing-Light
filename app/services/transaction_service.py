"""Transaction policy, serialization, and inventory mutation helpers."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import (
    ApprovalTask,
    FollowUpTask,
    MaintenanceRecord,
    Resource,
    ResourceItem,
    Transaction,
    User,
)
from app.services.alert_service import emit_alert
from app.services.auth_service import is_teacher_or_admin
from app.services.evidence_policy_service import ensure_evidence_backfill_task
from app.services.resource_item_service import (
    ensure_resource_item_capacity,
    get_transaction_items,
    is_tracked_resource,
    link_items_to_transaction,
    mark_items_available,
    mark_items_lost,
    mark_items_maintenance,
    reserve_items_for_borrow,
    sync_resource_available_count,
)
from app.services.rules_engine import run_inventory_rules, run_utilization_rules, run_waste_rules
from app.services.time_slot_service import calculate_duration, to_utc_naive

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
    borrow_time = to_utc_naive(tx.borrow_time)
    borrow_started = borrow_time is None or borrow_time <= datetime.utcnow()
    return bool(
        current_user
        and tx.user_id == current_user.id
        and tx.action == "borrow"
        and tx.status == "approved"
        and tx.return_time is None
        and borrow_started
    )


def build_transaction_out(tx: Transaction, current_user: Optional[User] = None) -> dict:
    """Serialize a transaction into a stable DTO."""
    resource = tx.resource
    requester = tx.user
    approval = tx.approval_task
    resource_item_ids = [link.resource_item_id for link in tx.item_links]
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
        "project_name": tx.project_name or "",
        "estimated_quantity": tx.estimated_quantity,
        "status": tx.status,
        "approval_status": get_approval_status(tx),
        "approval_id": approval.id if approval else None,
        "borrow_time": tx.borrow_time,
        "expected_return_time": tx.expected_return_time,
        "return_time": tx.return_time,
        "duration_minutes": tx.duration_minutes,
        "condition_return": tx.condition_return or "good",
        "evidence_url": tx.evidence_url or "",
        "evidence_type": tx.evidence_type or "",
        "resource_item_ids": resource_item_ids,
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
    if tx.action == "replenish":
        return "Suggest approve: replenishment request will increase available stock."
    if tx.action in {"borrow", "consume"} and tx.quantity > resource.available_count:
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


def _select_items_for_loss(
    db: Session,
    resource: Resource,
    quantity: int,
    preferred_item_ids: Optional[List[int]] = None,
) -> List[ResourceItem]:
    preferred_item_ids = preferred_item_ids or []
    candidates = (
        db.query(ResourceItem)
        .filter(
            ResourceItem.resource_id == resource.id,
            ResourceItem.status.in_(["available", "borrowed", "maintenance", "quarantine"]),
        )
        .order_by(ResourceItem.id.asc())
        .all()
    )
    preferred = [item for item in candidates if item.id in preferred_item_ids]
    remaining = [item for item in candidates if item.id not in preferred_item_ids]
    selected = (preferred + remaining)[:quantity]
    if len(selected) < quantity:
        raise ValueError("Not enough tracked instances to mark as lost")
    return selected


def _create_follow_up_task(
    db: Session,
    *,
    resource: Resource,
    transaction: Optional[Transaction],
    task_type: str,
    title: str,
    description: str,
    resource_item: Optional[ResourceItem] = None,
    assigned_user_id: Optional[int] = None,
    due_days: int = 3,
) -> None:
    db.add(
        FollowUpTask(
            transaction_id=transaction.id if transaction else None,
            resource_id=resource.id,
            resource_item_id=resource_item.id if resource_item else None,
            assigned_user_id=assigned_user_id,
            task_type=task_type,
            title=title,
            description=description,
            due_at=datetime.utcnow() + timedelta(days=due_days),
        )
    )


def _create_maintenance_record(
    db: Session,
    *,
    item: ResourceItem,
    actor: Optional[User],
    description: str,
    evidence_url: str = "",
    evidence_type: str = "",
) -> None:
    db.add(
        MaintenanceRecord(
            resource_item_id=item.id,
            recorded_by_user_id=actor.id if actor else None,
            status=item.status,
            description=description,
            evidence_url=evidence_url,
            evidence_type=evidence_type,
        )
    )


def apply_inventory_change(
    db: Session,
    tx: Transaction,
    preferred_item_ids: Optional[List[int]] = None,
) -> Transaction:
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
        if tx.action == "borrow" and is_tracked_resource(resource):
            if not tx.user:
                raise ValueError("Borrow transaction user is missing")
            reserve_items_for_borrow(db, tx, tx.user, preferred_item_ids)
        else:
            resource.available_count -= tx.quantity

    elif tx.action == "replenish":
        resource.total_count += tx.quantity
        resource.available_count += tx.quantity
        if is_tracked_resource(resource):
            ensure_resource_item_capacity(db, resource)
            sync_resource_available_count(db, resource)

    elif tx.action == "lost":
        if tx.quantity > resource.total_count:
            raise ValueError("Lost quantity exceeds total inventory")
        if is_tracked_resource(resource):
            selected_items = _select_items_for_loss(db, resource, tx.quantity, preferred_item_ids)
            available_lost = sum(1 for item in selected_items if item.status == "available")
            mark_items_lost(selected_items)
            link_items_to_transaction(db, tx, selected_items)
            resource.total_count -= len(selected_items)
            resource.available_count = max(0, resource.available_count - available_lost)
            for item in selected_items:
                _create_follow_up_task(
                    db,
                    resource=resource,
                    transaction=tx,
                    resource_item=item,
                    task_type="loss_investigation",
                    title=f"Investigate lost asset {item.asset_number}",
                    description=f"Asset {item.asset_number} was reported lost. Verify accountability and update records.",
                    assigned_user_id=tx.user_id,
                )
        else:
            resource.total_count -= tx.quantity
            resource.available_count = max(0, resource.available_count - tx.quantity)

    elif tx.action == "adjust":
        if tx.inventory_after_total is None or tx.inventory_after_available is None:
            raise ValueError("Adjustment targets are missing")
        if tx.inventory_after_available > tx.inventory_after_total:
            raise ValueError("Available inventory cannot exceed total inventory")
        if is_tracked_resource(resource):
            raise ValueError("Tracked device inventory should be adjusted through instance workflows")
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
    if tx.action == "lost":
        ensure_evidence_backfill_task(
            db,
            resource=resource,
            transaction=tx,
            evidence_url=tx.evidence_url or "",
            evidence_type=tx.evidence_type or "",
            scenario="报失登记",
            assigned_user_id=tx.user_id,
        )
    return tx


def apply_return(
    db: Session,
    tx: Transaction,
    condition_return: str,
    note: str = "",
    *,
    return_time: Optional[datetime] = None,
    lost_quantity: int = 0,
    evidence_url: str = "",
    evidence_type: str = "",
    actor: Optional[User] = None,
) -> Transaction:
    """Close an approved borrow record and restore availability."""
    if tx.action != "borrow":
        raise ValueError("Only borrow records can be returned")
    if tx.status != "approved":
        raise ValueError("Only approved borrow records can be returned")
    if tx.return_time is not None:
        raise ValueError("This borrow record has already been returned")
    if not tx.resource:
        raise ValueError("Transaction resource is missing")

    actual_return_time = to_utc_naive(return_time) or datetime.utcnow()
    borrow_time = to_utc_naive(tx.borrow_time)
    if borrow_time and actual_return_time < borrow_time:
        raise ValueError("return_time must be later than or equal to borrow_time")

    resource = tx.resource
    before_available = resource.available_count
    linked_items = get_transaction_items(tx)

    if condition_return == "partial_lost":
        if lost_quantity <= 0 or lost_quantity > tx.quantity:
            raise ValueError("partial_lost returns must include a valid lost_quantity")
    elif lost_quantity:
        raise ValueError("lost_quantity is only allowed for partial_lost returns")

    if is_tracked_resource(resource):
        ensure_resource_item_capacity(db, resource)

    if condition_return == "good":
        if linked_items:
            mark_items_available(linked_items, resource.location)
            sync_resource_available_count(db, resource)
        else:
            resource.available_count = min(resource.total_count, resource.available_count + tx.quantity)

    elif condition_return == "damaged":
        if linked_items:
            mark_items_maintenance(linked_items, f"{resource.location} / quarantine", quarantine=True)
            sync_resource_available_count(db, resource)
            for item in linked_items:
                _create_maintenance_record(
                    db,
                    item=item,
                    actor=actor,
                    description=f"Returned as damaged in transaction #{tx.id}. {note}".strip(),
                    evidence_url=evidence_url,
                    evidence_type=evidence_type,
                )
                _create_follow_up_task(
                    db,
                    resource=resource,
                    transaction=tx,
                    resource_item=item,
                    task_type="maintenance",
                    title=f"Inspect damaged asset {item.asset_number}",
                    description=f"Borrow transaction #{tx.id} returned {item.asset_number} as damaged. Move through maintenance or quarantine.",
                    assigned_user_id=actor.id if actor else None,
                )
        else:
            # For non-tracked resources, damaged returns do not re-enter available inventory.
            resource.available_count = before_available

    elif condition_return == "partial_lost":
        returned_count = tx.quantity - lost_quantity
        if linked_items:
            lost_items = linked_items[:lost_quantity]
            returned_items = linked_items[lost_quantity:]
            mark_items_lost(lost_items)
            mark_items_available(returned_items, resource.location)
            resource.total_count = max(0, resource.total_count - len(lost_items))
            sync_resource_available_count(db, resource)
        else:
            resource.total_count = max(0, resource.total_count - lost_quantity)
            resource.available_count = min(resource.total_count, before_available + returned_count)

        _create_follow_up_task(
            db,
            resource=resource,
            transaction=tx,
            task_type="accountability",
            title=f"Accountability review for partial loss on {resource.name}",
            description=f"Transaction #{tx.id} returned with partial loss ({lost_quantity}/{tx.quantity}). Confirm borrower responsibility.",
            assigned_user_id=tx.user_id,
            due_days=2,
        )
        _create_follow_up_task(
            db,
            resource=resource,
            transaction=tx,
            task_type="registry_backfill",
            title=f"Backfill registry after partial loss on {resource.name}",
            description=f"Update asset registry and replacement plan after partial loss in transaction #{tx.id}.",
            assigned_user_id=actor.id if actor else None,
            due_days=5,
        )
    else:
        raise ValueError("Unsupported return condition")

    if condition_return in {"damaged", "partial_lost"}:
        ensure_evidence_backfill_task(
            db,
            resource=resource,
            transaction=tx,
            evidence_url=evidence_url or "",
            evidence_type=evidence_type or "",
            scenario="异常归还",
            assigned_user_id=(actor.id if actor else tx.user_id),
        )

    tx.return_time = actual_return_time
    tx.condition_return = condition_return
    tx.duration_minutes = calculate_duration(borrow_time, tx.return_time) if borrow_time else None
    tx.return_inventory_before_available = before_available
    tx.return_inventory_after_available = resource.available_count
    tx.status = "returned"
    if note:
        tx.note = append_note(tx.note, f"Return note: {note}")
    if evidence_url:
        tx.evidence_url = evidence_url
    if evidence_type:
        tx.evidence_type = evidence_type

    run_inventory_rules(db, resource)
    run_utilization_rules(db, resource)

    if condition_return == "damaged":
        emit_alert(
            db,
            level="warn",
            alert_type="return_exception",
            message=f"Resource [{resource.name}] was returned damaged and moved to maintenance/quarantine.",
            dedup_key=f"return_exception:resource:{resource.id}",
        )
    elif condition_return == "partial_lost":
        emit_alert(
            db,
            level="error",
            alert_type="partial_loss",
            message=f"Resource [{resource.name}] was returned with partial loss in transaction #{tx.id}.",
            dedup_key=f"partial_loss:resource:{resource.id}",
        )

    return tx
