"""Borrow time-slot helpers."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Transaction


def to_utc_naive(value: Optional[datetime]) -> Optional[datetime]:
    """Normalize aware datetimes to UTC-naive for consistent DB comparisons."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def check_time_slot_conflict(
    db: Session,
    resource_id: int,
    borrow_time: datetime,
    return_time: datetime,
    exclude_transaction_id: Optional[int] = None,
    *,
    requested_quantity: int = 1,
    capacity: Optional[int] = None,
) -> List[Transaction]:
    """Return blocking overlap records for one requested borrow slot.

    Behavior:
    - When ``capacity`` is None, any overlap is considered conflict (legacy mode).
    - When ``capacity`` is provided, only return overlap records when
      ``overlap_quantity + requested_quantity > capacity``.
    """
    borrow_time = to_utc_naive(borrow_time)
    return_time = to_utc_naive(return_time)

    if borrow_time is None or return_time is None:
        raise ValueError("borrow_time and expected_return_time are required")
    if borrow_time >= return_time:
        raise ValueError("expected_return_time must be later than borrow_time")

    conflicts = (
        db.query(Transaction)
        .filter(
            Transaction.resource_id == resource_id,
            Transaction.action == "borrow",
            Transaction.status == "approved",
            Transaction.return_time.is_(None),
            Transaction.borrow_time.isnot(None),
            Transaction.expected_return_time.isnot(None),
        )
        .all()
    )

    result = []
    for tx in conflicts:
        if exclude_transaction_id and tx.id == exclude_transaction_id:
            continue

        tx_start = to_utc_naive(tx.borrow_time)
        tx_end = to_utc_naive(tx.expected_return_time or tx.return_time) or (datetime.utcnow() + timedelta(days=365))
        if max(borrow_time, tx_start) < min(return_time, tx_end):
            result.append(tx)

    if capacity is None:
        return result

    overlap_quantity = sum(max(int(tx.quantity or 1), 1) for tx in result)
    needed_quantity = max(int(requested_quantity or 1), 1)
    return result if overlap_quantity + needed_quantity > max(int(capacity), 0) else []


def calculate_duration(borrow_time: datetime, return_time: Optional[datetime]) -> Optional[int]:
    """Calculate borrow duration in minutes."""
    borrow = to_utc_naive(borrow_time)
    returned = to_utc_naive(return_time)
    if returned is None:
        return None
    if borrow is None:
        return None
    delta = returned - borrow
    return int(delta.total_seconds() / 60)
