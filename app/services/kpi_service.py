"""KPI dashboard service for finals evaluation evidence."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session, joinedload

from app.models import Resource, Transaction


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _borrow_hours(tx: Transaction) -> float:
    if not tx.borrow_time:
        return 0.0
    end_time = tx.return_time or tx.expected_return_time
    if not end_time or end_time <= tx.borrow_time:
        return 0.0
    return max(0.0, (end_time - tx.borrow_time).total_seconds() / 3600)


def _gini(values: List[float]) -> float:
    cleaned = [value for value in values if value >= 0]
    if not cleaned:
        return 0.0
    sorted_values = sorted(cleaned)
    total = sum(sorted_values)
    if total == 0:
        return 0.0
    weighted_sum = sum((index + 1) * value for index, value in enumerate(sorted_values))
    n = len(sorted_values)
    return (2 * weighted_sum) / (n * total) - (n + 1) / n


def _window(days: int, *, offset_days: int = 0) -> Tuple[datetime, datetime]:
    end = datetime.utcnow() - timedelta(days=offset_days)
    start = end - timedelta(days=days)
    return start, end


def _load_transactions(db: Session, start: datetime, end: datetime) -> List[Transaction]:
    return (
        db.query(Transaction)
        .options(joinedload(Transaction.resource))
        .filter(Transaction.created_at >= start, Transaction.created_at <= end)
        .all()
    )


def _utilization_rate(db: Session, rows: List[Transaction], start: datetime, end: datetime) -> float:
    devices = db.query(Resource).filter(Resource.category == "device", Resource.total_count > 0).all()
    if not devices:
        return 0.0

    borrow_rows = [tx for tx in rows if tx.action == "borrow" and tx.status in {"approved", "returned"}]
    days = max(1, int((end - start).total_seconds() / 86400))
    values = []
    for resource in devices:
        usage_hours = sum(_borrow_hours(tx) for tx in borrow_rows if tx.resource_id == resource.id)
        capacity_hours = max(resource.total_count, 1) * days * 14
        values.append(_safe_ratio(usage_hours, capacity_hours))
    return round(sum(values) / len(values), 4) if values else 0.0


def _overdue_rate(rows: List[Transaction]) -> float:
    borrow_rows = [
        tx
        for tx in rows
        if tx.action == "borrow" and tx.status in {"approved", "returned"} and tx.expected_return_time is not None
    ]
    if not borrow_rows:
        return 0.0
    now = datetime.utcnow()
    overdue_count = 0
    for tx in borrow_rows:
        if tx.return_time is not None and tx.return_time > tx.expected_return_time:
            overdue_count += 1
        elif tx.return_time is None and tx.expected_return_time < now:
            overdue_count += 1
    return _safe_ratio(overdue_count, len(borrow_rows))


def _waste_rate(rows: List[Transaction]) -> float:
    consume_rows = [
        tx
        for tx in rows
        if tx.action == "consume" and tx.status in {"approved", "returned"}
    ]
    total_qty = sum(tx.quantity for tx in consume_rows)
    if total_qty <= 0:
        return 0.0

    risk_qty = 0
    for tx in consume_rows:
        threshold = 10
        if tx.resource is not None:
            threshold = max(int(tx.resource.min_threshold or 0) * 2, 10)
        if tx.quantity >= threshold:
            risk_qty += tx.quantity
    return _safe_ratio(risk_qty, total_qty)


def _loss_rate(rows: List[Transaction], start: datetime, end: datetime) -> float:
    loss_events = [tx for tx in rows if tx.action == "lost" and tx.status in {"approved", "returned"}]
    borrow_events = [tx for tx in rows if tx.action == "borrow" and tx.status in {"approved", "returned"}]
    partial_loss_returns = [
        tx
        for tx in borrow_events
        if tx.condition_return == "partial_lost" and tx.return_time is not None and start <= tx.return_time <= end
    ]
    denominator = len(borrow_events) + len(loss_events)
    numerator = len(loss_events) + len(partial_loss_returns)
    return _safe_ratio(numerator, denominator) if denominator else 0.0


def _fairness_index(rows: List[Transaction]) -> float:
    borrow_rows = [tx for tx in rows if tx.action == "borrow" and tx.status in {"approved", "returned"}]
    per_user_hours: Dict[int, float] = defaultdict(float)
    for tx in borrow_rows:
        per_user_hours[tx.user_id] += _borrow_hours(tx)
    if not per_user_hours:
        return 1.0
    gini = _gini(list(per_user_hours.values()))
    return round(1 - gini, 4)


def _collect_metric_values(
    db: Session,
    *,
    current_rows: List[Transaction],
    baseline_rows: List[Transaction],
    current_start: datetime,
    current_end: datetime,
    baseline_start: datetime,
    baseline_end: datetime,
) -> Dict[str, Tuple[float, float]]:
    return {
        "utilization_rate": (
            _utilization_rate(db, current_rows, current_start, current_end),
            _utilization_rate(db, baseline_rows, baseline_start, baseline_end),
        ),
        "overdue_rate": (
            _overdue_rate(current_rows),
            _overdue_rate(baseline_rows),
        ),
        "waste_rate": (
            _waste_rate(current_rows),
            _waste_rate(baseline_rows),
        ),
        "loss_rate": (
            _loss_rate(current_rows, current_start, current_end),
            _loss_rate(baseline_rows, baseline_start, baseline_end),
        ),
        "fairness_index": (
            _fairness_index(current_rows),
            _fairness_index(baseline_rows),
        ),
    }


_KPI_DICTIONARY = [
    {
        "id": "utilization_rate",
        "name": "设备利用率",
        "unit": "ratio",
        "direction": "higher_better",
        "formula": "borrow_hours / capacity_hours",
        "description": "借用时长占可用容量时长的比例，反映设备周转与价值释放。",
    },
    {
        "id": "overdue_rate",
        "name": "逾期率",
        "unit": "ratio",
        "direction": "lower_better",
        "formula": "overdue_borrows / total_borrows",
        "description": "借用记录中发生逾期的比例，反映借还纪律和治理效果。",
    },
    {
        "id": "waste_rate",
        "name": "浪费率",
        "unit": "ratio",
        "direction": "lower_better",
        "formula": "high_risk_consume_qty / total_consume_qty",
        "description": "高风险大批量耗材消耗占比，反映耗材浪费风险。",
    },
    {
        "id": "loss_rate",
        "name": "报失率",
        "unit": "ratio",
        "direction": "lower_better",
        "formula": "(lost_events + partial_loss_returns) / (borrow_events + lost_events)",
        "description": "报失与部分丢失事件占比，反映资产丢失控制能力。",
    },
    {
        "id": "fairness_index",
        "name": "公平指数",
        "unit": "score",
        "direction": "higher_better",
        "formula": "1 - gini(user_borrow_hours)",
        "description": "用户借用时长分布公平性，越接近 1 越均衡。",
    },
]


def _build_metric_item(defn: Dict[str, str], current_value: float, baseline_value: float) -> Dict:
    higher_better = defn["direction"] == "higher_better"
    improvement = round(current_value - baseline_value, 4) if higher_better else round(baseline_value - current_value, 4)

    if baseline_value == 0:
        improvement_pct = 0.0
    else:
        improvement_pct = round((improvement / abs(baseline_value)) * 100, 2)

    if improvement > 0:
        trend = "improved"
        interpretation = "相较基线已改善"
    elif improvement < 0:
        trend = "declined"
        interpretation = "相较基线有回退"
    else:
        trend = "stable"
        interpretation = "与基线持平"

    return {
        "id": defn["id"],
        "name": defn["name"],
        "unit": defn["unit"],
        "direction": defn["direction"],
        "formula": defn["formula"],
        "description": defn["description"],
        "baseline_value": baseline_value,
        "current_value": current_value,
        "improvement_value": improvement,
        "improvement_percent": improvement_pct,
        "trend": trend,
        "interpretation": interpretation,
    }


def build_kpi_dashboard(db: Session, days: int = 30) -> Dict:
    """Build KPI board with baseline comparison and metric dictionary."""
    days = max(7, min(int(days), 180))

    current_start, current_end = _window(days, offset_days=0)
    baseline_start, baseline_end = _window(days, offset_days=days)
    current_rows = _load_transactions(db, current_start, current_end)
    baseline_rows = _load_transactions(db, baseline_start, baseline_end)

    values = _collect_metric_values(
        db,
        current_rows=current_rows,
        baseline_rows=baseline_rows,
        current_start=current_start,
        current_end=current_end,
        baseline_start=baseline_start,
        baseline_end=baseline_end,
    )

    metrics = [
        _build_metric_item(defn, values[defn["id"]][0], values[defn["id"]][1])
        for defn in _KPI_DICTIONARY
    ]

    return {
        "period": {
            "days": days,
            "current_start": current_start,
            "current_end": current_end,
            "baseline_start": baseline_start,
            "baseline_end": baseline_end,
        },
        "metrics": metrics,
        "dictionary": _KPI_DICTIONARY,
        "generated_at": datetime.utcnow(),
    }
