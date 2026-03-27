"""Rule-based business tools for the lab assistant."""

import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models import ApprovalTask, Resource, Transaction, User
from app.services.smart_scheduler import get_optimal_time_slots


def _find_resource_from_question(db: Session, question: str) -> Optional[Resource]:
    question_lower = question.lower()
    resources = db.query(Resource).all()
    best_match = None
    best_score = 0
    for resource in resources:
        candidates = [resource.name.lower(), resource.subtype.lower()]
        score = sum(1 for candidate in candidates if candidate and candidate in question_lower)
        if score > best_score:
            best_match = resource
            best_score = score
    return best_match


def _parse_duration_minutes(question: str) -> int:
    match = re.search(r"(\d+)\s*(小时|h|hour|hours)", question, re.IGNORECASE)
    if match:
        return int(match.group(1)) * 60

    match = re.search(r"(\d+)\s*(分钟|min|mins|minute|minutes)", question, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return 120


def _parse_preferred_start(question: str) -> Optional[datetime]:
    now = datetime.utcnow()
    if "明天下午" in question:
        return (now + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
    if "明天上午" in question:
        return (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    if "今天下午" in question:
        return now.replace(hour=14, minute=0, second=0, microsecond=0)
    if "今天上午" in question:
        return now.replace(hour=9, minute=0, second=0, microsecond=0)
    return None


def _inventory_tool(db: Session, question: str) -> Dict[str, str]:
    resource = _find_resource_from_question(db, question)
    if resource:
        answer = (
            f"{resource.name} 当前可用 {resource.available_count}/{resource.total_count}。"
            f" 低库存阈值是 {resource.min_threshold}，状态为 {resource.status}。"
        )
        if resource.available_count <= resource.min_threshold:
            answer += " 这项资源已经进入低库存预警。"
        return {"intent": "inventory_status", "answer": answer}

    low_items = (
        db.query(Resource)
        .filter(Resource.available_count <= Resource.min_threshold)
        .order_by(Resource.available_count.asc())
        .limit(10)
        .all()
    )
    if not low_items:
        return {"intent": "inventory_status", "answer": "当前没有低库存资源，库存状态整体健康。"}

    lines = [
        f"- {item.name}: 可用 {item.available_count}/{item.total_count}，阈值 {item.min_threshold}"
        for item in low_items
    ]
    return {"intent": "inventory_status", "answer": "以下资源需要优先关注补货：\n" + "\n".join(lines)}


def _approval_tool(db: Session) -> Dict[str, str]:
    pending = db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "pending").scalar() or 0
    approved = db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "approved").scalar() or 0
    rejected = db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "rejected").scalar() or 0

    lines = [
        f"待审批 {pending} 条",
        f"已通过 {approved} 条",
        f"已拒绝 {rejected} 条",
    ]

    if pending:
        tasks = (
            db.query(ApprovalTask)
            .options(
                joinedload(ApprovalTask.transaction).joinedload(Transaction.resource),
                joinedload(ApprovalTask.requester),
            )
            .filter(ApprovalTask.status == "pending")
            .order_by(ApprovalTask.created_at.desc())
            .limit(3)
            .all()
        )
        lines.append("最近待审批：")
        for task in tasks:
            tx = task.transaction
            resource_name = tx.resource.name if tx and tx.resource else f"Resource#{tx.resource_id}"
            requester_name = task.requester.real_name if task.requester else f"User#{task.requester_id}"
            lines.append(f"- {requester_name} 申请 {tx.action} {resource_name} x{tx.quantity}")

    return {"intent": "approval_status", "answer": "\n".join(lines)}


def _schedule_tool(db: Session, question: str) -> Dict[str, str]:
    resource = _find_resource_from_question(db, question)
    if not resource:
        return {
            "intent": "schedule_recommendation",
            "answer": "请先说明具体设备名称，例如“3D打印机”或“激光切割机”，我才能推荐空档。",
        }
    if resource.category != "device":
        return {
            "intent": "schedule_recommendation",
            "answer": f"{resource.name} 是耗材资源，不适用时段排程。",
        }

    duration_minutes = _parse_duration_minutes(question)
    preferred_start = _parse_preferred_start(question)
    slots = get_optimal_time_slots(db, resource.id, duration_minutes, preferred_start)
    if not slots:
        return {
            "intent": "schedule_recommendation",
            "answer": f"目前没有为 {resource.name} 生成可用时段，请稍后重试。",
        }

    lines = [f"{resource.name} 的推荐时段如下："]
    for slot in slots[:3]:
        lines.append(
            f"- {slot['start'].strftime('%Y-%m-%d %H:%M')} 到 {slot['end'].strftime('%H:%M')}，"
            f"评分 {slot['score']:.0f}"
        )

    best = slots[0]
    recommendation = (
        f"建议优先选择 {best['start'].strftime('%Y-%m-%d %H:%M')} 开始的时段，"
        f"因为它冲突最少且综合评分最高。"
    )
    return {"intent": "schedule_recommendation", "answer": "\n".join(lines + [recommendation])}


def _anomaly_tool(db: Session) -> Dict[str, str]:
    recent_txs = (
        db.query(Transaction)
        .options(joinedload(Transaction.resource), joinedload(Transaction.user))
        .filter(
            Transaction.action.in_(["consume", "lost"]),
            Transaction.status.in_(["approved", "returned"]),
            Transaction.created_at >= datetime.utcnow() - timedelta(days=30),
        )
        .all()
    )

    if not recent_txs:
        return {"intent": "anomaly_analysis", "answer": "最近 30 天没有发现异常领用或丢失记录。"}

    stats = defaultdict(lambda: {"quantity": 0, "count": 0})
    for tx in recent_txs:
        key = (
            tx.user.real_name if tx.user else f"User#{tx.user_id}",
            tx.resource.name if tx.resource else f"Resource#{tx.resource_id}",
        )
        stats[key]["quantity"] += tx.quantity
        stats[key]["count"] += 1

    ranked = sorted(stats.items(), key=lambda item: (item[1]["quantity"], item[1]["count"]), reverse=True)
    lines = ["最近 30 天值得关注的领用/丢失行为："]
    for (user_name, resource_name), data in ranked[:5]:
        lines.append(f"- {user_name}: {resource_name}，累计 {data['quantity']} 件，发生 {data['count']} 次")

    lines.append("建议把累计量高且频次高的记录优先交给教师或管理员复核。")
    return {"intent": "anomaly_analysis", "answer": "\n".join(lines)}


def _recommendation_tool(db: Session) -> Dict[str, str]:
    low_count = db.query(func.count(Resource.id)).filter(Resource.available_count <= Resource.min_threshold).scalar() or 0
    pending_approvals = db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "pending").scalar() or 0
    busy_devices = (
        db.query(Resource)
        .filter(Resource.category == "device", Resource.total_count > 0)
        .all()
    )

    lines = []
    if low_count:
        lines.append(f"- 当前有 {low_count} 个资源处于低库存，建议优先安排补货。")
    if pending_approvals:
        lines.append(f"- 当前有 {pending_approvals} 条待审批申请，建议尽快处理以免阻塞借用流程。")
    for device in busy_devices:
        occupancy = 1 - (device.available_count / device.total_count)
        if occupancy >= 0.8:
            lines.append(f"- {device.name} 占用率约 {occupancy:.0%}，建议增加设备或错峰预约。")

    if not lines:
        lines.append("- 当前资源运营状态平稳，可以继续保持现有管理策略。")
    return {"intent": "recommendation", "answer": "\n".join(lines)}


def run_business_tool(db: Session, question: str) -> Dict[str, str]:
    """Select and execute the most relevant business tool."""
    q = question.lower()
    if any(keyword in question for keyword in ["空档", "有空", "排程", "预约", "明天", "今天"]):
        return _schedule_tool(db, question)
    if any(keyword in question for keyword in ["审批", "待审", "待审批", "通过", "拒绝"]):
        return _approval_tool(db)
    if any(keyword in question for keyword in ["异常", "消耗", "领料", "浪费", "丢失"]):
        return _anomaly_tool(db)
    if any(keyword in question for keyword in ["库存", "缺货", "补货", "可用"]):
        return _inventory_tool(db, question)
    if any(keyword in q for keyword in ["建议", "optimize", "优化"]):
        return _recommendation_tool(db)
    return _recommendation_tool(db)


def ask_agent(db: Session, question: str) -> Dict[str, str]:
    """Public agent entry point."""
    result = run_business_tool(db, question)
    return {"intent": result["intent"], "answer": result["answer"]}
