"""Lightweight scheduling and resource optimization helpers."""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import Resource, Transaction


class SmartScheduler:
    """Provide simple scheduling recommendations for device resources."""

    def __init__(self, db: Session):
        self.db = db

    def get_optimal_time_slots(
        self,
        resource_id: int,
        duration_minutes: int,
        preferred_start: Optional[datetime] = None,
    ) -> List[Dict]:
        resource = self.db.query(Resource).filter(Resource.id == resource_id).first()
        if not resource or resource.category != "device":
            return []

        base_time = preferred_start or datetime.utcnow()
        base_time = max(base_time, datetime.utcnow())
        self._preferred_hour = preferred_start.hour if preferred_start else None
        candidates = self._generate_time_slots(base_time, duration_minutes)
        capacity = max(int(resource.total_count or 0), 1)

        scored = []
        for slot in candidates:
            conflicts = self._check_conflicts(resource_id, slot["start"], slot["end"], capacity)
            slot["conflicts"] = conflicts
            slot["score"] = self._score_time_slot(resource_id, slot["start"], slot["end"], len(conflicts))
            scored.append(slot)

        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:5]

    def _generate_time_slots(self, base_time: datetime, duration_minutes: int) -> List[Dict]:
        slots: List[Dict] = []
        start_day = base_time.replace(hour=8, minute=0, second=0, microsecond=0)
        for day_offset in range(7):
            day_base = start_day + timedelta(days=day_offset)
            for hour in range(8, 21, 2):
                start = day_base.replace(hour=hour)
                if start < base_time:
                    continue
                end = start + timedelta(minutes=duration_minutes)
                if end.hour > 22 or (end.hour == 22 and end.minute > 0):
                    continue
                slots.append(
                    {
                        "start": start,
                        "end": end,
                        "day": start.date().isoformat(),
                        "hour": start.hour,
                    }
                )
        return slots

    def _check_conflicts(self, resource_id: int, start_time: datetime, end_time: datetime, capacity: int) -> List[Dict]:
        conflicts = (
            self.db.query(Transaction)
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
        overlap_quantity = 0
        for tx in conflicts:
            if max(start_time, tx.borrow_time) < min(end_time, tx.expected_return_time):
                overlap_quantity += max(int(tx.quantity or 1), 1)
                result.append(
                    {
                        "transaction_id": tx.id,
                        "user_id": tx.user_id,
                        "quantity": tx.quantity,
                        "borrow_time": tx.borrow_time.isoformat() if tx.borrow_time else None,
                        "expected_return_time": tx.expected_return_time.isoformat() if tx.expected_return_time else None,
                    }
                )
        return result if overlap_quantity >= capacity else []

    def _score_time_slot(
        self,
        resource_id: int,
        start_time: datetime,
        end_time: datetime,
        conflict_count: int,
    ) -> float:
        score = 100.0
        if conflict_count:
            score -= 80

        if start_time.weekday() >= 5:
            score -= 10
        if 9 <= start_time.hour <= 17:
            score += 8

        # 优先匹配preferred_start的时间段
        if hasattr(self, '_preferred_hour') and self._preferred_hour is not None:
            hour_diff = abs(start_time.hour - self._preferred_hour)
            if hour_diff <= 2:
                score += 20
            elif hour_diff <= 4:
                score += 10

        recent_history = self._historical_usage(resource_id, start_time.weekday(), start_time.hour)
        score -= min(recent_history * 5, 20)

        hours_from_now = (start_time - datetime.utcnow()).total_seconds() / 3600
        if 0 <= hours_from_now <= 24:
            score += 5
        elif hours_from_now > 72:
            score -= 5

        return max(0.0, min(100.0, score))

    def _historical_usage(self, resource_id: int, weekday: int, hour: int) -> int:
        four_weeks_ago = datetime.utcnow() - timedelta(days=28)
        records = (
            self.db.query(Transaction)
            .filter(
                Transaction.resource_id == resource_id,
                Transaction.action == "borrow",
                Transaction.status.in_(["approved", "returned"]),
                Transaction.borrow_time.isnot(None),
                Transaction.borrow_time >= four_weeks_ago,
            )
            .all()
        )
        return sum(1 for tx in records if tx.borrow_time.weekday() == weekday and tx.borrow_time.hour == hour)

    def predict_resource_demand(self, resource_id: int, days_ahead: int = 7) -> List[Dict]:
        predictions: List[Dict] = []
        today = datetime.utcnow().date()
        history = (
            self.db.query(Transaction)
            .filter(
                Transaction.resource_id == resource_id,
                Transaction.action == "borrow",
                Transaction.status.in_(["approved", "returned"]),
                Transaction.borrow_time.isnot(None),
                Transaction.borrow_time >= datetime.utcnow() - timedelta(days=56),
            )
            .all()
        )

        for offset in range(days_ahead):
            target_date = today + timedelta(days=offset)
            weekday = target_date.weekday()
            matching = [tx for tx in history if tx.borrow_time.weekday() == weekday]
            predicted = round(len(matching) / 8, 2) if matching else 0.5
            recommendation = "High demand expected" if predicted >= 3 else "Normal demand expected" if predicted >= 1 else "Low demand expected"
            predictions.append(
                {
                    "date": target_date.isoformat(),
                    "predicted_demand": predicted,
                    "confidence": 0.8 if matching else 0.5,
                    "recommendation": recommendation,
                }
            )
        return predictions

    def optimize_resource_allocation(self) -> Dict:
        devices = self.db.query(Resource).filter(Resource.category == "device").all()
        recommendations: List[Dict] = []
        for device in devices:
            utilization = self._calculate_device_utilization(device.id)
            if utilization >= 0.85:
                recommendations.append(
                    {
                        "resource_id": device.id,
                        "resource_name": device.name,
                        "utilization": utilization,
                        "recommendation": "High utilization. Consider adding devices or spreading bookings.",
                        "priority": "high",
                    }
                )
            elif utilization <= 0.25:
                recommendations.append(
                    {
                        "resource_id": device.id,
                        "resource_name": device.name,
                        "utilization": utilization,
                        "recommendation": "Low utilization. Consider promotion or opening new teaching scenarios.",
                        "priority": "medium",
                    }
                )

        return {
            "total_devices": len(devices),
            "recommendations": recommendations,
            "generated_at": datetime.utcnow(),
        }

    def _calculate_device_utilization(self, resource_id: int) -> float:
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        usage_records = (
            self.db.query(Transaction)
            .filter(
                Transaction.resource_id == resource_id,
                Transaction.action == "borrow",
                Transaction.status.in_(["approved", "returned"]),
                Transaction.borrow_time.isnot(None),
                Transaction.borrow_time >= thirty_days_ago,
            )
            .all()
        )

        if not usage_records:
            return 0.0

        total_hours = 0.0
        for record in usage_records:
            end_time = record.return_time or record.expected_return_time
            if record.borrow_time and end_time:
                total_hours += max((end_time - record.borrow_time).total_seconds() / 3600, 0)

        max_possible_hours = 14 * 30
        return min(1.0, total_hours / max_possible_hours) if max_possible_hours else 0.0


def get_optimal_time_slots(
    db: Session,
    resource_id: int,
    duration_minutes: int,
    preferred_start: Optional[datetime] = None,
) -> List[Dict]:
    """Public wrapper for optimal slot recommendations."""
    scheduler = SmartScheduler(db)
    return scheduler.get_optimal_time_slots(resource_id, duration_minutes, preferred_start)


def predict_resource_demand(db: Session, resource_id: int, days_ahead: int = 7) -> List[Dict]:
    """Public wrapper for demand prediction."""
    scheduler = SmartScheduler(db)
    return scheduler.predict_resource_demand(resource_id, days_ahead)


def optimize_resource_allocation(db: Session) -> Dict:
    """Public wrapper for optimization recommendations."""
    scheduler = SmartScheduler(db)
    return scheduler.optimize_resource_allocation()


