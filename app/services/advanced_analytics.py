"""Advanced analytics service."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models import Resource, Transaction, User


def _clamp_score(value: float) -> float:
    return max(0.0, min(100.0, round(value, 2)))


def _borrow_end(tx: Transaction) -> Optional[datetime]:
    return tx.return_time or tx.expected_return_time


def _borrow_hours(tx: Transaction) -> float:
    if not tx.borrow_time:
        return 0.0
    end_time = _borrow_end(tx)
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


def _prime_window(day: date) -> tuple[datetime, datetime]:
    if day.weekday() < 5:
        return (
            datetime.combine(day, time(hour=18, minute=0)),
            datetime.combine(day, time(hour=22, minute=0)),
        )
    return (
        datetime.combine(day, time(hour=10, minute=0)),
        datetime.combine(day, time(hour=18, minute=0)),
    )


def _prime_time_overlap_hours(start: Optional[datetime], end: Optional[datetime]) -> float:
    if not start or not end or end <= start:
        return 0.0
    total = 0.0
    current_day = start.date()
    while current_day <= end.date():
        window_start, window_end = _prime_window(current_day)
        overlap_start = max(start, window_start)
        overlap_end = min(end, window_end)
        if overlap_end > overlap_start:
            total += (overlap_end - overlap_start).total_seconds() / 3600
        current_day += timedelta(days=1)
    return total


class AdvancedAnalytics:
    """Analytics calculator for overview, fairness, and anomaly scoring."""

    def __init__(self, db: Session):
        self.db = db

    def _window(self, days: int) -> tuple[datetime, datetime]:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        return start_date, end_date

    def _load_transactions(self, start_date: datetime, end_date: datetime) -> List[Transaction]:
        return (
            self.db.query(Transaction)
            .options(joinedload(Transaction.resource), joinedload(Transaction.user))
            .filter(Transaction.created_at >= start_date, Transaction.created_at <= end_date)
            .all()
        )

    def _load_borrow_transactions(self, start_date: datetime, end_date: datetime) -> List[Transaction]:
        return [
            tx
            for tx in self._load_transactions(start_date, end_date)
            if tx.action == "borrow" and tx.status in {"approved", "returned"}
        ]

    def get_comprehensive_analytics(self, days: int = 30) -> Dict:
        """Return the composite analytics report."""
        start_date, end_date = self._window(days)
        transactions = self._load_transactions(start_date, end_date)
        borrow_transactions = [tx for tx in transactions if tx.action == "borrow" and tx.status in {"approved", "returned"}]
        fairness_metrics = self._fairness_metrics(borrow_transactions)
        overdue_returns = self._overdue_returns()
        prime_monopolies = self._prime_time_monopolies(borrow_transactions)
        project_variance = self._project_usage_variance(transactions)

        return {
            "period": {
                "start_date": start_date.date().isoformat(),
                "end_date": end_date.date().isoformat(),
                "days": days,
            },
            "summary": self._summary_stats(transactions, borrow_transactions, start_date, end_date),
            "resource_analysis": self._resource_analysis(transactions, borrow_transactions, start_date, end_date),
            "user_behavior": self._user_behavior(transactions),
            "cost_analysis": self._cost_analysis(transactions, start_date, end_date),
            "trends": self._trends(transactions),
            "recommendations": self._recommendations(borrow_transactions, project_variance),
            "fairness_metrics": fairness_metrics,
            "overdue_returns": overdue_returns,
            "prime_time_monopolies": prime_monopolies,
            "project_usage_variance": project_variance,
            "anomaly_scores": self._anomaly_scores(transactions, overdue_returns, prime_monopolies, project_variance),
        }

    def _summary_stats(
        self,
        transactions: List[Transaction],
        borrow_transactions: List[Transaction],
        start_date: datetime,
        end_date: datetime,
    ) -> Dict:
        material_consumption = sum(tx.quantity for tx in transactions if tx.action in {"consume", "lost"})
        active_users = len({tx.user_id for tx in transactions})

        device_resources = self.db.query(Resource).filter(Resource.category == "device").all()
        utilization_values = []
        days = max(1, (end_date - start_date).days)
        for resource in device_resources:
            usage_hours = sum(
                _borrow_hours(tx)
                for tx in borrow_transactions
                if tx.resource_id == resource.id
            )
            capacity_hours = max(resource.total_count, 1) * days * 14
            utilization_values.append(usage_hours / capacity_hours if capacity_hours else 0.0)

        return {
            "total_transactions": len(transactions),
            "active_users": active_users,
            "average_device_utilization": round(sum(utilization_values) / len(utilization_values), 4)
            if utilization_values
            else 0.0,
            "material_consumption": material_consumption,
            "daily_avg_transactions": round(len(transactions) / days, 2),
        }

    def _resource_analysis(
        self,
        transactions: List[Transaction],
        borrow_transactions: List[Transaction],
        start_date: datetime,
        end_date: datetime,
    ) -> Dict:
        resource_counts = defaultdict(int)
        for tx in transactions:
            resource_counts[tx.resource_id] += 1

        popular_resources = []
        for resource_id, usage_count in sorted(resource_counts.items(), key=lambda item: item[1], reverse=True)[:10]:
            resource = next((tx.resource for tx in transactions if tx.resource_id == resource_id and tx.resource), None)
            popular_resources.append(
                {
                    "resource_id": resource_id,
                    "name": resource.name if resource else f"Resource#{resource_id}",
                    "usage_count": usage_count,
                }
            )

        high_utilization_devices = []
        days = max(1, (end_date - start_date).days)
        for resource in self.db.query(Resource).filter(Resource.category == "device").all():
            usage_hours = sum(_borrow_hours(tx) for tx in borrow_transactions if tx.resource_id == resource.id)
            capacity_hours = max(resource.total_count, 1) * days * 14
            utilization = usage_hours / capacity_hours if capacity_hours else 0.0
            if utilization >= 0.7:
                high_utilization_devices.append(
                    {
                        "resource_id": resource.id,
                        "name": resource.name,
                        "utilization": round(utilization, 4),
                        "usage_hours": round(usage_hours, 2),
                    }
                )

        return {
            "popular_resources": popular_resources,
            "high_utilization_devices": high_utilization_devices,
            "analysis_period": f"{start_date.date()} to {end_date.date()}",
        }

    def _user_behavior(self, transactions: List[Transaction]) -> Dict:
        top_users = defaultdict(int)
        user_patterns = defaultdict(int)
        for tx in transactions:
            top_users[(tx.user_id, tx.user.real_name if tx.user else f"User#{tx.user_id}")] += 1
            hour = tx.borrow_time.hour if tx.borrow_time else tx.created_at.hour
            user_patterns[(tx.user_id, hour)] += 1

        top_user_rows = sorted(top_users.items(), key=lambda item: item[1], reverse=True)[:10]
        pattern_rows = sorted(user_patterns.items(), key=lambda item: (item[0][0], item[0][1]))

        return {
            "top_users": [
                {"user_id": user_id, "name": name, "transaction_count": count}
                for (user_id, name), count in top_user_rows
            ],
            "user_patterns": [
                {"user_id": user_id, "hour": hour, "count": count}
                for (user_id, hour), count in pattern_rows
            ],
        }

    def _cost_analysis(self, transactions: List[Transaction], start_date: datetime, end_date: datetime) -> Dict:
        cost_breakdown = []
        total_cost = 0.0
        grouped = defaultdict(lambda: {"name": "", "quantity": 0, "unit_cost": 0.0})
        for tx in transactions:
            if tx.action not in {"consume", "lost"} or not tx.resource:
                continue
            bucket = grouped[tx.resource_id]
            bucket["name"] = tx.resource.name
            bucket["unit_cost"] = tx.resource.unit_cost or 0.0
            bucket["quantity"] += tx.quantity

        for resource_id, bucket in grouped.items():
            cost = bucket["quantity"] * bucket["unit_cost"]
            total_cost += cost
            cost_breakdown.append(
                {
                    "resource_id": resource_id,
                    "name": bucket["name"],
                    "quantity": bucket["quantity"],
                    "unit_cost": bucket["unit_cost"],
                    "total_cost": round(cost, 2),
                }
            )

        cost_breakdown.sort(key=lambda item: item["total_cost"], reverse=True)
        period_days = max(1, (end_date - start_date).days)
        return {
            "total_cost": round(total_cost, 2),
            "daily_avg_cost": round(total_cost / period_days, 2),
            "cost_breakdown": cost_breakdown[:10],
            "high_cost_items": [item for item in cost_breakdown if total_cost and item["total_cost"] >= total_cost * 0.1],
        }

    def _trends(self, transactions: List[Transaction]) -> Dict:
        daily_usage = defaultdict(int)
        category_usage = defaultdict(int)
        for tx in transactions:
            tx_day = tx.created_at.date().isoformat()
            daily_usage[tx_day] += 1
            category = tx.resource.category if tx.resource else "unknown"
            category_usage[(category, tx_day)] += 1

        return {
            "daily_usage": [
                {"date": tx_day, "count": count}
                for tx_day, count in sorted(daily_usage.items(), key=lambda item: item[0])
            ],
            "resource_category_trends": [
                {"category": category, "date": tx_day, "count": count}
                for (category, tx_day), count in sorted(category_usage.items(), key=lambda item: (item[0][1], item[0][0]))
            ],
        }

    def _fairness_metrics(self, borrow_transactions: List[Transaction]) -> Dict:
        per_user_hours = defaultdict(float)
        for tx in borrow_transactions:
            per_user_hours[tx.user_id] += _borrow_hours(tx)

        values = list(per_user_hours.values())
        total = sum(values)
        gini = _gini(values)
        top_user_share = max(values) / total if total else 0.0
        fairness_index = 1 - gini if values else 1.0
        return {
            "fairness_index": round(fairness_index, 4),
            "gini_coefficient": round(gini, 4),
            "top_user_share": round(top_user_share, 4),
            "active_user_count": len(per_user_hours),
        }

    def _overdue_returns(self) -> List[Dict]:
        now = datetime.utcnow()
        overdue = (
            self.db.query(Transaction)
            .options(joinedload(Transaction.resource), joinedload(Transaction.user))
            .filter(
                Transaction.action == "borrow",
                Transaction.status == "approved",
                Transaction.return_time.is_(None),
                Transaction.expected_return_time.isnot(None),
                Transaction.expected_return_time < now,
            )
            .order_by(Transaction.expected_return_time.asc())
            .all()
        )
        return [
            {
                "transaction_id": tx.id,
                "resource_id": tx.resource_id,
                "resource_name": tx.resource.name if tx.resource else f"Resource#{tx.resource_id}",
                "user_id": tx.user_id,
                "user_name": tx.user.real_name if tx.user else f"User#{tx.user_id}",
                "overdue_hours": round((now - tx.expected_return_time).total_seconds() / 3600, 2),
                "borrow_time": tx.borrow_time,
                "expected_return_time": tx.expected_return_time,
            }
            for tx in overdue
        ]

    def _prime_time_monopolies(self, borrow_transactions: List[Transaction]) -> List[Dict]:
        by_resource_user = defaultdict(lambda: {"hours": 0.0, "count": 0, "resource_name": "", "user_name": ""})
        resource_totals = defaultdict(float)

        for tx in borrow_transactions:
            overlap_hours = _prime_time_overlap_hours(tx.borrow_time, _borrow_end(tx))
            if overlap_hours <= 0:
                continue
            key = (tx.resource_id, tx.user_id)
            bucket = by_resource_user[key]
            bucket["hours"] += overlap_hours
            bucket["count"] += 1
            bucket["resource_name"] = tx.resource.name if tx.resource else f"Resource#{tx.resource_id}"
            bucket["user_name"] = tx.user.real_name if tx.user else f"User#{tx.user_id}"
            resource_totals[tx.resource_id] += overlap_hours

        monopolies = []
        for (resource_id, user_id), bucket in by_resource_user.items():
            total_hours = resource_totals[resource_id]
            share = bucket["hours"] / total_hours if total_hours else 0.0
            if bucket["hours"] >= 2 and share >= 0.5:
                monopolies.append(
                    {
                        "resource_id": resource_id,
                        "resource_name": bucket["resource_name"],
                        "user_id": user_id,
                        "user_name": bucket["user_name"],
                        "prime_time_hours": round(bucket["hours"], 2),
                        "prime_time_share": round(share, 4),
                        "borrow_count": bucket["count"],
                    }
                )

        monopolies.sort(key=lambda item: (item["prime_time_share"], item["prime_time_hours"]), reverse=True)
        return monopolies[:10]

    def _project_usage_variance(self, transactions: List[Transaction]) -> List[Dict]:
        estimates = defaultdict(int)
        actuals = defaultdict(int)

        for tx in transactions:
            if not tx.project_name:
                continue
            estimates[tx.project_name] += tx.estimated_quantity if tx.estimated_quantity is not None else tx.quantity
            if tx.status in {"approved", "returned"}:
                actuals[tx.project_name] += tx.quantity

        rows = []
        for project_name in sorted(set(estimates) | set(actuals)):
            estimated = estimates[project_name]
            actual = actuals[project_name]
            variance = actual - estimated
            variance_ratio = (variance / estimated) if estimated else 0.0
            rows.append(
                {
                    "project_name": project_name,
                    "estimated_quantity": estimated,
                    "actual_quantity": actual,
                    "variance": variance,
                    "variance_ratio": round(variance_ratio, 4),
                }
            )

        rows.sort(key=lambda item: abs(item["variance_ratio"]), reverse=True)
        return rows[:20]

    def _recommendations(self, borrow_transactions: List[Transaction], project_variance: List[Dict]) -> List[Dict]:
        recommendations = []
        overdue = self._overdue_returns()
        if overdue:
            item = overdue[0]
            recommendations.append(
                {
                    "type": "overdue_return",
                    "resource_id": item["resource_id"],
                    "resource_name": item["resource_name"],
                    "message": f"{item['resource_name']} 有超时未归还记录，建议优先催还并限制重复占用。",
                    "priority": "high",
                }
            )

        device_resources = self.db.query(Resource).filter(Resource.category == "device").all()
        for resource in device_resources:
            usage_hours = sum(_borrow_hours(tx) for tx in borrow_transactions if tx.resource_id == resource.id)
            if usage_hours >= 40:
                recommendations.append(
                    {
                        "type": "high_utilization",
                        "resource_id": resource.id,
                        "resource_name": resource.name,
                        "message": f"{resource.name} 使用时长偏高，建议扩容或实行错峰调度。",
                        "priority": "medium",
                    }
                )

        for item in project_variance[:3]:
            if abs(item["variance_ratio"]) >= 0.3:
                recommendations.append(
                    {
                        "type": "project_variance",
                        "resource_id": 0,
                        "resource_name": item["project_name"],
                        "message": f"项目 {item['project_name']} 的预计用量与实际偏差较大，建议补齐预算和复盘。",
                        "priority": "medium",
                    }
                )

        return recommendations[:10]

    def _anomaly_scores(
        self,
        transactions: List[Transaction],
        overdue_returns: List[Dict],
        prime_monopolies: List[Dict],
        project_variance: List[Dict],
    ) -> Dict:
        user_scores = defaultdict(lambda: {"name": "", "score": 0.0, "reasons": []})
        project_scores = defaultdict(lambda: {"name": "", "score": 0.0, "reasons": []})
        resource_scores = defaultdict(lambda: {"name": "", "score": 0.0, "reasons": []})

        for item in overdue_returns:
            user_bucket = user_scores[item["user_id"]]
            user_bucket["name"] = item["user_name"]
            user_bucket["score"] += min(30.0, item["overdue_hours"] * 2)
            user_bucket["reasons"].append(f"超时未归还 {item['resource_name']}")

            resource_bucket = resource_scores[item["resource_id"]]
            resource_bucket["name"] = item["resource_name"]
            resource_bucket["score"] += 15.0
            resource_bucket["reasons"].append("存在超时未归还")

        for item in prime_monopolies:
            user_bucket = user_scores[item["user_id"]]
            user_bucket["name"] = item["user_name"]
            user_bucket["score"] += item["prime_time_share"] * 20
            user_bucket["reasons"].append(f"黄金时段占用 {item['resource_name']} 占比 {item['prime_time_share']:.0%}")

            resource_bucket = resource_scores[item["resource_id"]]
            resource_bucket["name"] = item["resource_name"]
            resource_bucket["score"] += item["prime_time_share"] * 15
            resource_bucket["reasons"].append("黄金时段被高集中度占用")

        for tx in transactions:
            resource_name = tx.resource.name if tx.resource else f"Resource#{tx.resource_id}"
            user_name = tx.user.real_name if tx.user else f"User#{tx.user_id}"
            project_name = tx.project_name or ""

            if tx.action == "lost":
                user_scores[tx.user_id]["name"] = user_name
                user_scores[tx.user_id]["score"] += 35
                user_scores[tx.user_id]["reasons"].append(f"报失 {resource_name}")

                resource_scores[tx.resource_id]["name"] = resource_name
                resource_scores[tx.resource_id]["score"] += 30
                resource_scores[tx.resource_id]["reasons"].append("发生报失")

                if project_name:
                    project_scores[project_name]["name"] = project_name
                    project_scores[project_name]["score"] += 30
                    project_scores[project_name]["reasons"].append(f"关联资源报失 {resource_name}")

            if tx.condition_return == "damaged":
                user_scores[tx.user_id]["name"] = user_name
                user_scores[tx.user_id]["score"] += 20
                user_scores[tx.user_id]["reasons"].append(f"归还损坏 {resource_name}")

                resource_scores[tx.resource_id]["name"] = resource_name
                resource_scores[tx.resource_id]["score"] += 15
                resource_scores[tx.resource_id]["reasons"].append("发生损坏归还")

            if tx.condition_return == "partial_lost":
                user_scores[tx.user_id]["name"] = user_name
                user_scores[tx.user_id]["score"] += 30
                user_scores[tx.user_id]["reasons"].append(f"部分丢失 {resource_name}")

                resource_scores[tx.resource_id]["name"] = resource_name
                resource_scores[tx.resource_id]["score"] += 25
                resource_scores[tx.resource_id]["reasons"].append("发生部分丢失")

                if project_name:
                    project_scores[project_name]["name"] = project_name
                    project_scores[project_name]["score"] += 25
                    project_scores[project_name]["reasons"].append(f"关联部分丢失 {resource_name}")

        for item in project_variance:
            if abs(item["variance_ratio"]) < 0.3:
                continue
            bucket = project_scores[item["project_name"]]
            bucket["name"] = item["project_name"]
            bucket["score"] += min(40.0, abs(item["variance_ratio"]) * 100)
            bucket["reasons"].append(
                f"预计 vs 实际偏差 {item['variance_ratio']:.0%}"
            )

        return {
            "users": self._sorted_scores(user_scores),
            "projects": self._sorted_scores(project_scores),
            "resources": self._sorted_scores(resource_scores),
        }

    def _sorted_scores(self, buckets: Dict) -> List[Dict]:
        rows = []
        for key, bucket in buckets.items():
            if bucket["score"] <= 0:
                continue
            unique_reasons = []
            for reason in bucket["reasons"]:
                if reason not in unique_reasons:
                    unique_reasons.append(reason)
            rows.append(
                {
                    "key": str(key),
                    "name": bucket["name"] or str(key),
                    "anomaly_score": _clamp_score(bucket["score"]),
                    "reasons": unique_reasons[:5],
                }
            )
        rows.sort(key=lambda item: item["anomaly_score"], reverse=True)
        return rows[:10]

    def predict_future_demand(self, resource_id: int, days_ahead: int = 30) -> Dict:
        """Predict future demand from recent historical patterns."""
        predictions = []
        today = datetime.utcnow().date()
        eight_weeks_ago = today - timedelta(weeks=8)

        historical = (
            self.db.query(Transaction)
            .filter(
                Transaction.resource_id == resource_id,
                Transaction.action == "borrow",
                Transaction.borrow_time.isnot(None),
                Transaction.borrow_time >= datetime.combine(eight_weeks_ago, time.min),
                Transaction.status.in_(["approved", "returned"]),
            )
            .all()
        )

        for day_offset in range(days_ahead):
            target_date = today + timedelta(days=day_offset)
            matching = [tx for tx in historical if tx.borrow_time and tx.borrow_time.weekday() == target_date.weekday()]
            predicted_demand = round(sum(tx.quantity for tx in matching) / max(1, len(matching)), 2) if matching else 1.0
            confidence = round(min(1.0, len(matching) / 8), 2)
            recommendation = "按常规库存准备" if predicted_demand <= 1.5 else "建议提前预留或扩容"
            predictions.append(
                {
                    "date": target_date.isoformat(),
                    "predicted_demand": predicted_demand,
                    "confidence": confidence,
                    "recommendation": recommendation,
                }
            )

        return {
            "resource_id": resource_id,
            "days_ahead": days_ahead,
            "predictions": predictions,
            "prediction_method": "8_week_same_weekday_average",
            "generated_at": datetime.utcnow(),
        }


def get_comprehensive_analytics(db: Session, days: int = 30) -> Dict:
    """Public composite analytics entry point."""
    analytics = AdvancedAnalytics(db)
    return analytics.get_comprehensive_analytics(days)


def predict_future_demand(db: Session, resource_id: int, days_ahead: int = 30) -> Dict:
    """Public demand prediction entry point."""
    analytics = AdvancedAnalytics(db)
    return analytics.predict_future_demand(resource_id, days_ahead)
