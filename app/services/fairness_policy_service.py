"""Fairness policy runtime config and scoring helpers for scheduler."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Transaction

_DEFAULT_POLICY: Dict[str, object] = {
    "enabled": True,
    "golden_hours_enabled": True,
    "golden_hour_start": 9,
    "golden_hour_end": 18,
    "golden_time_quota_ratio": 0.35,
    "golden_time_penalty": 10.0,
    "consecutive_limit_enabled": True,
    "max_consecutive_bookings": 2,
    "consecutive_penalty": 18.0,
    "high_freq_penalty_enabled": True,
    "weekly_borrow_threshold": 6,
    "high_freq_penalty": 8.0,
    "updated_at": datetime.utcnow(),
}

_RUNTIME_POLICY: Dict[str, object] = deepcopy(_DEFAULT_POLICY)


def get_fairness_policy_config() -> Dict[str, object]:
    """Return runtime fairness policy config."""
    return deepcopy(_RUNTIME_POLICY)


def update_fairness_policy_config(payload: Dict[str, object]) -> Dict[str, object]:
    """Partially update fairness policy config."""
    for key, value in payload.items():
        if key not in _RUNTIME_POLICY or value is None:
            continue
        _RUNTIME_POLICY[key] = value
    _RUNTIME_POLICY["updated_at"] = datetime.utcnow()
    return get_fairness_policy_config()


def build_user_fairness_profile(
    db: Session,
    requester_user_id: Optional[int],
    resource_id: int,
    now: Optional[datetime] = None,
) -> Dict[str, float]:
    """Build user usage profile used by fairness scoring."""
    now = now or datetime.utcnow()
    if requester_user_id is None:
        return {
            "weekly_borrow_count": 0.0,
            "open_same_resource_count": 0.0,
            "golden_hours_ratio": 0.0,
        }

    history = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == requester_user_id,
            Transaction.action == "borrow",
            Transaction.status.in_(["approved", "returned"]),
            Transaction.borrow_time.isnot(None),
            Transaction.borrow_time >= now - timedelta(days=30),
        )
        .all()
    )

    weekly_borrow_count = sum(1 for tx in history if tx.borrow_time and tx.borrow_time >= now - timedelta(days=7))

    open_same_resource_count = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == requester_user_id,
            Transaction.resource_id == resource_id,
            Transaction.action == "borrow",
            Transaction.status == "approved",
            Transaction.return_time.is_(None),
        )
        .count()
    )

    total_hours = 0.0
    golden_hours = 0.0
    policy = get_fairness_policy_config()
    golden_start = int(policy["golden_hour_start"])
    golden_end = int(policy["golden_hour_end"])
    for tx in history:
        start = tx.borrow_time
        end = tx.return_time or tx.expected_return_time
        if not start or not end or end <= start:
            continue
        hours = max((end - start).total_seconds() / 3600, 0)
        total_hours += hours
        if golden_start <= start.hour < golden_end:
            golden_hours += hours

    golden_ratio = (golden_hours / total_hours) if total_hours > 0 else 0.0
    return {
        "weekly_borrow_count": float(weekly_borrow_count),
        "open_same_resource_count": float(open_same_resource_count),
        "golden_hours_ratio": float(golden_ratio),
    }


def evaluate_fairness_penalty(
    *,
    slot_start: datetime,
    policy: Dict[str, object],
    profile: Dict[str, float],
) -> Tuple[float, List[str]]:
    """Return fairness penalty and explanation reasons."""
    if not bool(policy.get("enabled", True)):
        return 0.0, []

    penalty = 0.0
    reasons: List[str] = []
    slot_hour = slot_start.hour

    if bool(policy.get("golden_hours_enabled", True)):
        golden_start = int(policy.get("golden_hour_start", 9))
        golden_end = int(policy.get("golden_hour_end", 18))
        is_golden_slot = golden_start <= slot_hour < golden_end
        if is_golden_slot and profile.get("golden_hours_ratio", 0.0) >= float(policy.get("golden_time_quota_ratio", 0.35)):
            golden_penalty = float(policy.get("golden_time_penalty", 10.0))
            penalty += golden_penalty
            reasons.append("黄金时段占比偏高，触发公平配额惩罚")

    if bool(policy.get("consecutive_limit_enabled", True)):
        open_count = profile.get("open_same_resource_count", 0.0)
        limit = float(policy.get("max_consecutive_bookings", 2))
        if open_count >= limit:
            consecutive_penalty = float(policy.get("consecutive_penalty", 18.0))
            penalty += consecutive_penalty
            reasons.append("同资源连续占用次数已达上限，触发限流惩罚")

    if bool(policy.get("high_freq_penalty_enabled", True)):
        weekly_count = profile.get("weekly_borrow_count", 0.0)
        threshold = float(policy.get("weekly_borrow_threshold", 6))
        if weekly_count >= threshold:
            high_freq_penalty = float(policy.get("high_freq_penalty", 8.0))
            penalty += high_freq_penalty
            reasons.append("近7天借用频率过高，触发高频降权惩罚")

    return penalty, reasons
