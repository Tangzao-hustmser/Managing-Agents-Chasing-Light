"""Tool selection and execution for the agent assistant."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models import Alert, ApprovalTask, ChatSession, Resource, Transaction, User
from app.services.approval_service import approve_task, get_approval_by_id, reject_task
from app.services.auth_service import is_admin, is_teacher_or_admin
from app.services.smart_scheduler import get_optimal_time_slots
from app.services.time_slot_service import check_time_slot_conflict
from app.services.transaction_service import apply_inventory_change, build_transaction_out, validate_resource_action


_RESOURCE_ALIAS_HINTS = (
    (("3d", "printer", "打印机", "ender"), ["3d打印机", "3d printer", "打印机", "ender-3", "ender3"]),
    (("laser", "激光", "cutter"), ["激光切割机", "激光机", "laser cutter"]),
    (("multimeter", "万用表"), ["万用表", "multimeter", "数字万用表"]),
    (("development", "arduino", "esp", "开发板"), ["开发板", "arduino", "esp32", "esp8266"]),
    (("component", "electronic", "元器件"), ["电子元器件", "元器件", "电阻", "电容"]),
)

_SCHEDULE_KEYWORDS = {
    "空档",
    "有空",
    "排程",
    "预约",
    "时段",
    "档期",
    "可用",
    "能用",
    "什么时候",
    "几点",
    "schedule",
    "slot",
    "book",
}
_SCHEDULE_USAGE_HINTS = {"用", "借", "使用", "安排", "预约", "book", "reserve", "schedule"}
_SCHEDULE_TIME_HINTS = {"今天", "明天", "后天", "上午", "下午", "晚上", "周", "点", ":", "："}

_GOVERNANCE_KEYWORDS = {
    "利用率",
    "占用不均",
    "均衡",
    "耗材浪费",
    "浪费",
    "工具丢失",
    "资源丢失",
    "优化建议",
    "治理建议",
    "怎么改进",
    "怎么优化",
}


def _normalize_text(value: str) -> str:
    return re.sub(r"[\s\-_]+", "", value.lower())


def _extract_tokens(value: str) -> List[str]:
    return [token for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", value.lower()) if len(token) >= 2]


def _resource_aliases(resource: Resource) -> List[str]:
    aliases = set()
    for value in [resource.name or "", resource.subtype or ""]:
        if not value:
            continue
        aliases.add(value.lower())
        aliases.update(_extract_tokens(value))

    merged = _normalize_text(f"{resource.name} {resource.subtype}")
    for matchers, extra_aliases in _RESOURCE_ALIAS_HINTS:
        if any(matcher in merged for matcher in matchers):
            aliases.update(extra_aliases)
    return [alias for alias in aliases if alias]


def _resource_match_score(resource: Resource, question: str) -> int:
    question_lower = question.lower()
    question_normalized = _normalize_text(question)
    score = 0
    for alias in _resource_aliases(resource):
        normalized_alias = _normalize_text(alias)
        if not normalized_alias:
            continue
        if normalized_alias in question_normalized:
            score += 6 if len(normalized_alias) >= 4 else 3
        elif alias in question_lower:
            score += 2
    return score


def _find_resource_from_question(db: Session, question: str) -> Optional[Resource]:
    resources = db.query(Resource).all()
    best_match = None
    best_score = 0
    for resource in resources:
        score = _resource_match_score(resource, question)
        if score > best_score:
            best_match = resource
            best_score = score
    return best_match


def _parse_quantity(question: str, default: int = 1) -> int:
    match = re.search(r"(?<![A-Za-z])(\d+)\s*(台|个|件|份|套|支|盒)\b", question)
    if match:
        return int(match.group(1))
    match = re.search(r"[xX*]\s*(\d+)", question)
    return int(match.group(1)) if match else default


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
    if "后天下午" in question:
        return (now + timedelta(days=2)).replace(hour=14, minute=0, second=0, microsecond=0)
    if "后天上午" in question:
        return (now + timedelta(days=2)).replace(hour=9, minute=0, second=0, microsecond=0)
    if "后天晚上" in question:
        return (now + timedelta(days=2)).replace(hour=19, minute=0, second=0, microsecond=0)
    if "明天下午" in question:
        return (now + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
    if "明天上午" in question:
        return (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    if "明天晚上" in question:
        return (now + timedelta(days=1)).replace(hour=19, minute=0, second=0, microsecond=0)
    if "今天下午" in question:
        return now.replace(hour=14, minute=0, second=0, microsecond=0)
    if "今天上午" in question:
        return now.replace(hour=9, minute=0, second=0, microsecond=0)
    if "今天晚上" in question:
        return now.replace(hour=19, minute=0, second=0, microsecond=0)
    if "后天" in question:
        return (now + timedelta(days=2)).replace(hour=14, minute=0, second=0, microsecond=0)
    if "明天" in question:
        return (now + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)

    match = re.search(r"(\d{4}-\d{2}-\d{2})\s*(\d{1,2})[点:：](\d{0,2})?", question)
    if match:
        hour = int(match.group(2))
        minute = int(match.group(3) or 0)
        return datetime.fromisoformat(match.group(1)).replace(hour=hour, minute=minute)
    return None


def _parse_project_name(question: str) -> str:
    match = re.search(r"(?:项目|project)[:： ]+([A-Za-z0-9_\-\u4e00-\u9fff]+)", question, re.IGNORECASE)
    return match.group(1) if match else ""


def _is_confirmation_message(message: str) -> bool:
    lowered = message.strip().lower()
    return lowered in {"确认", "执行", "同意", "yes", "y", "ok", "好的"} or "确认执行" in lowered


def _is_cancel_message(message: str) -> bool:
    lowered = message.strip().lower()
    return lowered in {"取消", "撤销", "不用了", "cancel", "no", "n"} or "取消执行" in lowered


def _is_schedule_question(question: str) -> bool:
    lowered = question.lower()
    has_schedule_keyword = any(keyword in lowered for keyword in _SCHEDULE_KEYWORDS)
    has_usage_and_time = any(keyword in lowered for keyword in _SCHEDULE_USAGE_HINTS) and any(
        keyword in lowered for keyword in _SCHEDULE_TIME_HINTS
    )
    return has_schedule_keyword or has_usage_and_time


def _slot_reason(slot: Dict, preferred_start: Optional[datetime]) -> str:
    reasons: List[str] = []
    conflicts = slot.get("conflicts", [])
    if conflicts:
        reasons.append(f"仅有 {len(conflicts)} 个冲突")
    else:
        reasons.append("无已批准借用冲突")

    if preferred_start:
        hour_gap = abs((slot["start"] - preferred_start).total_seconds()) / 3600
        if hour_gap <= 2:
            reasons.append("开始时间接近你提到的时段")
        elif hour_gap <= 4:
            reasons.append("时间点与需求较接近")

    score = float(slot.get("score", 0))
    if score >= 95:
        reasons.append("综合评分最高")
    elif score >= 85:
        reasons.append("综合评分较高")
    return "，".join(reasons)


def _format_schedule_reply(resource: Resource, slots: List[Dict], preferred_start: Optional[datetime]) -> str:
    free_slots = [slot for slot in slots if not slot.get("conflicts")]
    candidates = free_slots if free_slots else slots
    best_slot = candidates[0]
    best_start = best_slot["start"].strftime("%Y-%m-%d %H:%M")

    if free_slots:
        lines = [
            f"有空档。{resource.name} 可以安排使用。",
            f"建议你优先从 {best_start} 开始，{_slot_reason(best_slot, preferred_start)}。",
            "具体时段如下：",
        ]
    else:
        lines = [
            f"当前没有完全空档，但 {resource.name} 还有可协调时段。",
            f"建议先尝试 {best_start}，{_slot_reason(best_slot, preferred_start)}，可提前联系老师或管理员协调。",
            "可选时段如下：",
        ]

    for slot in candidates[:3]:
        conflicts = slot.get("conflicts", [])
        conflict_hint = "无冲突" if not conflicts else f"{len(conflicts)} 个冲突"
        lines.append(
            f"- {slot['start'].strftime('%Y-%m-%d %H:%M')} 到 {slot['end'].strftime('%H:%M')}（评分 {slot['score']:.0f}，{conflict_hint}）"
        )

    lines.append("如果你愿意，我可以继续帮你直接发起借用申请。")
    return "\n".join(lines)


def _build_governance_suggestions(db: Session) -> str:
    devices = db.query(Resource).filter(Resource.category == "device", Resource.total_count > 0).all()
    if not devices:
        return "当前没有设备类数据，暂时无法给出治理建议。"

    occupancy = sorted(
        [
            {
                "name": device.name,
                "rate": round(1 - (device.available_count / max(device.total_count, 1)), 4),
            }
            for device in devices
        ],
        key=lambda item: item["rate"],
        reverse=True,
    )
    most_busy = occupancy[0]
    least_busy = occupancy[-1]
    pending_approvals = db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "pending").scalar() or 0
    lost_records = db.query(func.count(Transaction.id)).filter(Transaction.action == "lost", Transaction.status == "approved").scalar() or 0
    partial_loss_returns = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.action == "borrow", Transaction.status == "returned", Transaction.condition_return == "partial_lost")
        .scalar()
        or 0
    )
    high_consume_events = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.action == "consume", Transaction.status.in_(["approved", "returned"]), Transaction.quantity >= 10)
        .scalar()
        or 0
    )

    return (
        "结合当前数据，建议优先做这 3 件事：\n"
        f"1. 均衡占用：{most_busy['name']} 当前占用率约 {most_busy['rate']:.0%}，而 {least_busy['name']} 约 {least_busy['rate']:.0%}，"
        "建议优先把新预约引导到低占用设备。\n"
        f"2. 控制浪费：近期高量领用事件 {high_consume_events} 次，建议对大额领用启用二次确认和项目预算校验。\n"
        f"3. 降低丢失风险：报失 {lost_records} 次、部分丢失归还 {partial_loss_returns} 次，建议增加借还拍照留证与归还验收清单。\n"
        f"补充：当前待审批 {pending_approvals} 条，可优先处理设备借用审批以提升周转效率。"
    )


def ensure_chat_session(db: Session, session_id: Optional[str], owner: User) -> ChatSession:
    """Fetch or create an owner-bound chat session."""
    sid = session_id or uuid.uuid4().hex
    session = db.query(ChatSession).filter(ChatSession.session_id == sid).first()
    if session and session.owner_user_id != owner.id:
        raise ValueError("Session does not belong to the current user")
    if not session:
        session = ChatSession(session_id=sid, owner_user_id=owner.id)
        db.add(session)
        db.commit()
        db.refresh(session)
    return session


def list_user_sessions(db: Session, owner: User, limit: int = 20) -> List[str]:
    """Return recent session ids for one owner."""
    rows = (
        db.query(ChatSession.session_id)
        .filter(ChatSession.owner_user_id == owner.id)
        .order_by(ChatSession.updated_at.desc())
        .limit(limit)
        .all()
    )
    return [row[0] for row in rows]


def get_real_time_data_context(db: Session) -> Dict:
    """Build a compact real-time data snapshot for the agent."""
    low_inventory_resources = (
        db.query(Resource)
        .filter(Resource.available_count <= Resource.min_threshold)
        .order_by(Resource.available_count.asc())
        .limit(10)
        .all()
    )
    recent_alerts = db.query(Alert).order_by(Alert.created_at.desc()).limit(5).all()
    pending_approvals = db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "pending").scalar() or 0

    return {
        "low_inventory_resources": [
            {
                "id": resource.id,
                "name": resource.name,
                "available_count": resource.available_count,
                "min_threshold": resource.min_threshold,
            }
            for resource in low_inventory_resources
        ],
        "pending_approvals": pending_approvals,
        "recent_alerts": [
            {
                "type": alert.type,
                "level": alert.level,
                "message": alert.message,
                "created_at": alert.created_at.isoformat(),
            }
            for alert in recent_alerts
        ],
    }


def run_business_query(db: Session, question: str) -> Dict[str, str]:
    """Answer a read-only question with deterministic business logic."""
    resource = _find_resource_from_question(db, question)

    if _is_schedule_question(question):
        if not resource:
            return {
                "intent": "schedule_recommendation",
                "answer": "请告诉我具体设备名称（例如 3D打印机、激光切割机、万用表），我再帮你查空档。",
            }
        duration_minutes = _parse_duration_minutes(question)
        preferred_start = _parse_preferred_start(question)
        slots = get_optimal_time_slots(db, resource.id, duration_minutes, preferred_start)
        if not slots:
            return {
                "intent": "schedule_recommendation",
                "answer": f"暂时没找到 {resource.name} 的合适空档。你可以换一个日期，或缩短预计使用时长后再试。",
            }
        return {
            "intent": "schedule_recommendation",
            "answer": _format_schedule_reply(resource, slots, preferred_start),
        }

    if any(keyword in question for keyword in ["审批", "待审", "通过", "拒绝"]):
        pending = db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "pending").scalar() or 0
        approved = db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "approved").scalar() or 0
        rejected = db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "rejected").scalar() or 0
        return {
            "intent": "approval_status",
            "answer": f"当前待审批 {pending} 条，已通过 {approved} 条，已拒绝 {rejected} 条。",
        }

    if any(keyword in question for keyword in _GOVERNANCE_KEYWORDS):
        return {
            "intent": "governance_recommendation",
            "answer": _build_governance_suggestions(db),
        }

    if any(keyword in question for keyword in ["异常", "超时", "逾期", "损坏", "丢失"]):
        overdue = (
            db.query(Transaction)
            .options(joinedload(Transaction.resource), joinedload(Transaction.user))
            .filter(
                Transaction.action == "borrow",
                Transaction.status == "approved",
                Transaction.expected_return_time.isnot(None),
                Transaction.expected_return_time < datetime.utcnow(),
                Transaction.return_time.is_(None),
            )
            .all()
        )
        if not overdue:
            return {"intent": "anomaly_analysis", "answer": "当前没有超时未归还记录。"}
        lines = ["超时未归还记录："]
        for tx in overdue[:5]:
            resource_name = tx.resource.name if tx.resource else f"Resource#{tx.resource_id}"
            user_name = tx.user.real_name if tx.user else f"User#{tx.user_id}"
            overdue_hours = round((datetime.utcnow() - tx.expected_return_time).total_seconds() / 3600, 1)
            lines.append(f"- {user_name} 占用 {resource_name}，已超时 {overdue_hours} 小时")
        return {"intent": "anomaly_analysis", "answer": "\n".join(lines)}

    if resource:
        item_suffix = ""
        if resource.category == "device":
            tracked_count = len([item for item in resource.items if item.status != "disabled"])
            item_suffix = f"，已建档实例 {tracked_count} 台"
        answer = (
            f"{resource.name} 当前可用 {resource.available_count}/{resource.total_count}"
            f"，阈值 {resource.min_threshold}，状态 {resource.status}{item_suffix}。"
        )
        return {"intent": "inventory_status", "answer": answer}

    low_count = db.query(func.count(Resource.id)).filter(Resource.available_count <= Resource.min_threshold).scalar() or 0
    return {
        "intent": "recommendation",
        "answer": f"当前共有 {low_count} 类资源处于低库存。你可以继续问我库存、审批、排程或异常治理问题。",
    }


def build_action_proposal(db: Session, current_user: User, question: str) -> Optional[Dict]:
    """Build a pending tool action if the user is asking for one."""
    resource = _find_resource_from_question(db, question)
    quantity = _parse_quantity(question)
    duration_minutes = _parse_duration_minutes(question)
    preferred_start = _parse_preferred_start(question)
    project_name = _parse_project_name(question)

    if any(keyword in question for keyword in ["申请借", "帮我借", "借用申请", "我要借"]) and resource:
        start = preferred_start or (datetime.utcnow() + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        end = start + timedelta(minutes=duration_minutes)
        return {
            "name": "submit_borrow_application",
            "title": f"提交借用申请：{resource.name} x{quantity}",
            "proposed_payload": {
                "resource_id": resource.id,
                "action": "borrow",
                "quantity": quantity,
                "borrow_time": start.isoformat(),
                "expected_return_time": end.isoformat(),
                "purpose": question,
                "project_name": project_name,
                "estimated_quantity": quantity,
            },
        }

    if any(keyword in question for keyword in ["申请领用", "领料", "领用"]) and resource:
        return {
            "name": "submit_consume_application",
            "title": f"提交领用申请：{resource.name} x{quantity}",
            "proposed_payload": {
                "resource_id": resource.id,
                "action": "consume",
                "quantity": quantity,
                "purpose": question,
                "project_name": project_name,
                "estimated_quantity": quantity,
            },
        }

    if any(keyword in question for keyword in ["补货", "补充库存", "补库存"]) and resource and is_admin(current_user):
        return {
            "name": "replenish_inventory",
            "title": f"补货入库：{resource.name} x{quantity}",
            "proposed_payload": {
                "resource_id": resource.id,
                "action": "replenish",
                "quantity": quantity,
                "purpose": question,
                "project_name": project_name,
            },
        }

    if any(keyword in question for keyword in ["报失", "登记丢失", "丢失登记"]) and resource and is_teacher_or_admin(current_user):
        return {
            "name": "report_loss",
            "title": f"登记报失：{resource.name} x{quantity}",
            "proposed_payload": {
                "resource_id": resource.id,
                "action": "lost",
                "quantity": quantity,
                "note": question,
                "purpose": "agent loss report",
                "project_name": project_name,
            },
        }

    if any(keyword in question for keyword in ["批准", "通过审批", "同意审批"]) and is_teacher_or_admin(current_user):
        match = re.search(r"(\d+)", question)
        if match:
            approval_id = int(match.group(1))
            return {
                "name": "approve_task",
                "title": f"通过审批 #{approval_id}",
                "proposed_payload": {"approval_id": approval_id, "reason": question},
            }

    if any(keyword in question for keyword in ["拒绝审批", "驳回审批", "不通过"]) and is_teacher_or_admin(current_user):
        match = re.search(r"(\d+)", question)
        if match:
            approval_id = int(match.group(1))
            return {
                "name": "reject_task",
                "title": f"拒绝审批 #{approval_id}",
                "proposed_payload": {"approval_id": approval_id, "reason": question},
            }

    return None


def store_pending_action(session: ChatSession, proposal: Dict) -> Dict:
    """Persist a pending action into the chat session."""
    confirmation_token = uuid.uuid4().hex
    payload = dict(proposal["proposed_payload"])
    payload["confirmation_token"] = confirmation_token
    session.pending_tool_name = proposal["name"]
    session.pending_tool_payload = json.dumps(payload, ensure_ascii=False)
    return {
        "name": proposal["name"],
        "title": proposal["title"],
        "confirmation_token": confirmation_token,
        "proposed_payload": payload,
    }


def clear_pending_action(session: ChatSession) -> None:
    """Clear a pending action from the session."""
    session.pending_tool_name = None
    session.pending_tool_payload = ""


def _execute_transaction_tool(db: Session, current_user: User, payload: Dict) -> Dict:
    resource = db.query(Resource).filter(Resource.id == payload["resource_id"]).first()
    if not resource:
        raise ValueError("Resource not found")

    action = payload["action"]
    quantity = int(payload.get("quantity", 1))
    if action in {"borrow", "consume"} and current_user.role not in {"student", "teacher"}:
        raise ValueError("Only students or teachers can submit applications")
    if action == "replenish" and not is_admin(current_user):
        raise ValueError("Only admins can replenish inventory")
    if action == "lost" and not is_teacher_or_admin(current_user):
        raise ValueError("Only teachers or admins can report loss")
    tx = Transaction(
        resource_id=resource.id,
        user_id=current_user.id,
        action=action,
        quantity=quantity,
        note=payload.get("note", ""),
        borrow_time=datetime.fromisoformat(payload["borrow_time"]) if payload.get("borrow_time") else None,
        expected_return_time=(
            datetime.fromisoformat(payload["expected_return_time"])
            if payload.get("expected_return_time")
            else None
        ),
        purpose=payload.get("purpose", ""),
        project_name=payload.get("project_name", ""),
        estimated_quantity=payload.get("estimated_quantity"),
        status="pending" if action in {"borrow", "consume"} else "approved",
        is_approved=action not in {"borrow", "consume"},
    )
    db.add(tx)
    db.flush()
    tx.resource = resource
    tx.user = current_user

    if action in {"borrow", "consume"}:
        validate_resource_action(resource, action)
        if action == "borrow":
            if not tx.borrow_time or not tx.expected_return_time:
                raise ValueError("Borrow request is missing borrow_time or expected_return_time")
            conflicts = check_time_slot_conflict(db, resource.id, tx.borrow_time, tx.expected_return_time)
            if conflicts:
                raise ValueError("Requested time slot conflicts with an approved borrow")
        from app.services.approval_service import create_approval_task

        create_approval_task(db, tx, current_user, reason="Agent-submitted request awaiting approval")
        db.commit()
        db.refresh(tx)
        return {
            "summary": f"已提交 {action} 申请，单号 #{tx.id}，等待审批。",
            "transaction": build_transaction_out(tx, current_user),
        }

    apply_inventory_change(db, tx)
    db.commit()
    db.refresh(tx)
    return {
        "summary": f"已执行 {action}，流水单号 #{tx.id}。",
        "transaction": build_transaction_out(tx, current_user),
    }


def execute_pending_action(db: Session, session: ChatSession, current_user: User, confirmation_token: Optional[str]) -> Dict:
    """Execute the pending action stored in one session."""
    if not session.pending_tool_name or not session.pending_tool_payload:
        raise ValueError("No pending action to confirm")

    payload = json.loads(session.pending_tool_payload)
    expected_token = payload.get("confirmation_token")
    if confirmation_token and confirmation_token != expected_token:
        raise ValueError("Confirmation token mismatch")

    tool_name = session.pending_tool_name
    if tool_name in {"submit_borrow_application", "submit_consume_application", "replenish_inventory", "report_loss"}:
        result = _execute_transaction_tool(db, current_user, payload)
    elif tool_name == "approve_task":
        if not is_teacher_or_admin(current_user):
            raise ValueError("Only teachers or admins can approve requests")
        approval_id = int(payload["approval_id"])
        task = get_approval_by_id(db, approval_id)
        if not task:
            raise ValueError("Approval task not found")
        task = approve_task(db, task, current_user, payload.get("reason", ""))
        db.commit()
        result = {"summary": f"已通过审批 #{task.id}。"}
    elif tool_name == "reject_task":
        if not is_teacher_or_admin(current_user):
            raise ValueError("Only teachers or admins can reject requests")
        approval_id = int(payload["approval_id"])
        task = get_approval_by_id(db, approval_id)
        if not task:
            raise ValueError("Approval task not found")
        task = reject_task(db, task, current_user, payload.get("reason", ""))
        db.commit()
        result = {"summary": f"已拒绝审批 #{task.id}。"}
    else:
        raise ValueError("Unsupported pending action")

    clear_pending_action(session)
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"name": tool_name, **result}
