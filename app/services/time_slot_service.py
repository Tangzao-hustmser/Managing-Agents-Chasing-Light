"""Borrow time-slot helpers."""

from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Transaction


def check_time_slot_conflict(
    db: Session,
    resource_id: int,
    borrow_time: datetime,
    return_time: datetime,
    exclude_transaction_id: Optional[int] = None,
) -> List[Transaction]:
    """Return approved borrow records that overlap the requested slot."""
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

        tx_start = tx.borrow_time
        tx_end = tx.expected_return_time or tx.return_time or (datetime.utcnow() + timedelta(days=365))
        if max(borrow_time, tx_start) < min(return_time, tx_end):
            result.append(tx)

    return result


def calculate_duration(borrow_time: datetime, return_time: Optional[datetime]) -> Optional[int]:
    """Calculate borrow duration in minutes."""
    if return_time is None:
        return None
    delta = return_time - borrow_time
    return int(delta.total_seconds() / 60)
