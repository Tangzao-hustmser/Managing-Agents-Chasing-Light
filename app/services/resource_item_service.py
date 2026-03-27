"""Helpers for tracked resource instances."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Resource, ResourceItem, Transaction, TransactionItem, User

TRACKED_STATUSES_AVAILABLE = {"available"}
TRACKED_STATUSES_UNAVAILABLE = {"borrowed", "maintenance", "quarantine", "lost", "disabled"}


def generate_asset_number(resource_id: int, index: int) -> str:
    """Generate a stable asset number."""
    return f"R{resource_id:04d}-{index:04d}"


def is_tracked_resource(resource: Resource) -> bool:
    """Whether this resource should be tracked by instance."""
    return resource.category == "device"


def ensure_resource_item_capacity(db: Session, resource: Resource) -> List[ResourceItem]:
    """Create missing resource-item rows for tracked device resources."""
    if not is_tracked_resource(resource):
        return []

    items = (
        db.query(ResourceItem)
        .filter(ResourceItem.resource_id == resource.id)
        .order_by(ResourceItem.id.asc())
        .all()
    )
    while len(items) < max(resource.total_count, 0):
        index = len(items) + 1
        item = ResourceItem(
            resource_id=resource.id,
            asset_number=generate_asset_number(resource.id, index),
            qr_code=f"qr://resource/{resource.id}/item/{index}",
            status="available",
            current_location=resource.location,
        )
        db.add(item)
        db.flush()
        items.append(item)
    return items


def get_resource_items(db: Session, resource_id: int) -> List[ResourceItem]:
    """List items for a resource."""
    return (
        db.query(ResourceItem)
        .filter(ResourceItem.resource_id == resource_id)
        .order_by(ResourceItem.id.asc())
        .all()
    )


def count_available_items(resource: Resource) -> int:
    """Count tracked available items."""
    return sum(1 for item in resource.items if item.status == "available")


def sync_resource_available_count(db: Session, resource: Resource) -> None:
    """Refresh aggregate available_count from tracked items."""
    if is_tracked_resource(resource):
        db.flush()
        resource.available_count = (
            db.query(func.count(ResourceItem.id))
            .filter(
                ResourceItem.resource_id == resource.id,
                ResourceItem.status == "available",
            )
            .scalar()
            or 0
        )


def link_items_to_transaction(db: Session, transaction: Transaction, items: Iterable[ResourceItem]) -> None:
    """Attach items to a transaction if not linked already."""
    existing_item_ids = {link.resource_item_id for link in transaction.item_links}
    for item in items:
        if item.id in existing_item_ids:
            continue
        db.add(TransactionItem(transaction_id=transaction.id, resource_item_id=item.id))
        existing_item_ids.add(item.id)


def get_transaction_items(transaction: Transaction) -> List[ResourceItem]:
    """Return linked resource items for one transaction."""
    return [link.resource_item for link in transaction.item_links if link.resource_item]


def reserve_items_for_borrow(
    db: Session,
    transaction: Transaction,
    current_user: User,
    preferred_item_ids: Optional[List[int]] = None,
) -> List[ResourceItem]:
    """Allocate available device instances to a borrow transaction."""
    resource = transaction.resource
    if not resource or not is_tracked_resource(resource):
        return []

    ensure_resource_item_capacity(db, resource)
    preferred_item_ids = preferred_item_ids or []

    available_items = (
        db.query(ResourceItem)
        .filter(
            ResourceItem.resource_id == resource.id,
            ResourceItem.status == "available",
        )
        .order_by(ResourceItem.id.asc())
        .all()
    )

    preferred = [item for item in available_items if item.id in preferred_item_ids]
    remaining = [item for item in available_items if item.id not in preferred_item_ids]
    selected = (preferred + remaining)[: transaction.quantity]
    if len(selected) < transaction.quantity:
        raise ValueError("Insufficient tracked device instances")

    for item in selected:
        item.status = "borrowed"
        item.current_borrower_id = current_user.id
        item.current_location = f"Borrowed by {current_user.real_name}"

    link_items_to_transaction(db, transaction, selected)
    sync_resource_available_count(db, resource)
    return selected


def mark_items_available(items: Iterable[ResourceItem], location: str) -> None:
    """Mark instances as available."""
    for item in items:
        item.status = "available"
        item.current_borrower_id = None
        item.current_location = location


def mark_items_maintenance(items: Iterable[ResourceItem], location: str, quarantine: bool = False) -> None:
    """Mark instances as maintenance or quarantine."""
    next_status = "quarantine" if quarantine else "maintenance"
    for item in items:
        item.status = next_status
        item.current_borrower_id = None
        item.current_location = location
        item.last_maintenance_at = datetime.utcnow()


def mark_items_lost(items: Iterable[ResourceItem]) -> None:
    """Mark instances as lost."""
    for item in items:
        item.status = "lost"
        item.current_borrower_id = None
        item.current_location = "Missing / lost"
