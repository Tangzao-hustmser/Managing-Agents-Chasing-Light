"""Tool selection and execution for the agent assistant."""

from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models import Alert, ApprovalTask, ChatSession, FollowUpTask, Resource, Transaction, User
from app.services.approval_service import approve_task, create_approval_task, get_approval_by_id, reject_task
from app.services.auth_service import is_admin, is_teacher_or_admin
from app.services.smart_scheduler import get_optimal_time_slots
from app.services.time_slot_service import check_time_slot_conflict, to_utc_naive
from app.services.transaction_service import (
    append_note,
    apply_inventory_change,
    build_transaction_out,
    validate_resource_action,
)


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

_REPLENISH_APPROVAL_ACTION_KEYWORDS = [
    "补货审批单",
    "生成补货审批",
    "一键补货审批",
    "按建议补货",
    "执行补货建议",
    "根据建议补货",
    "执行建议补货",
]

_FOLLOW_UP_QUERY_KEYWORDS = {
    "待办",
    "任务",
    "闭环",
    "后续",
    "追责",
    "维护任务",
    "follow-up",
}

_BORROW_ACTION_KEYWORDS = [
    "申请借",
    "帮我借",
    "借用申请",
    "提交借用",
    "我要借",
    "帮我预约",
    "帮我预定",
    "安排借用",
]

_CONSUME_ACTION_KEYWORDS = [
    "申请领用",
    "申请领料",
    "提交领用",
    "我要领用",
    "我要领料",
    "领料申请",
    "领用申请",
]

_REPLENISH_ACTION_KEYWORDS = [
    "补货",
    "补库存",
    "补充库存",
    "采购入库",
    "加库存",
]

_LOSS_ACTION_KEYWORDS = [
    "报失",
    "登记丢失",
    "丢失登记",
    "设备遗失",
    "物料遗失",
    "资源遗失",
]

_APPROVE_ACTION_KEYWORDS = [
    "通过审批",
    "批准审批",
    "审核通过",
    "同意审批",
    "批准申请",
    "通过申请",
]

_REJECT_ACTION_KEYWORDS = [
    "拒绝审批",
    "驳回审批",
    "不通过审批",
    "拒绝申请",
    "驳回申请",
]

_TASK_DONE_KEYWORDS = [
    "完成任务",
    "关闭任务",
    "任务完成",
    "处理完成",
    "结案任务",
    "完结任务",
    "done task",
]

_TASK_PROGRESS_KEYWORDS = [
    "开始任务",
    "开始处理",
    "跟进任务",
    "任务处理中",
    "着手处理任务",
]

_CONTEXT_REFERENCE_KEYWORDS = {"这个", "该", "这条", "上一条", "最新", "刚刚"}

_WEEKDAY_MAP = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
}

_PERIOD_DEFAULT_HOUR = {
    "早上": 9,
    "上午": 9,
    "中午": 12,
    "下午": 14,
    "晚上": 19,
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
    resources = db.query(Resource).filter(Resource.status != "disabled").all()
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


def _detect_period(question: str) -> Optional[str]:
    for period in ["早上", "上午", "中午", "下午", "晚上"]:
        if period in question:
            return period
    return None


def _normalize_hour(period: Optional[str], hour: int) -> int:
    normalized_hour = hour
    if period in {"下午", "晚上"} and 0 <= hour < 12:
        normalized_hour = hour + 12
    elif period == "中午" and 0 <= hour < 11:
        normalized_hour = hour + 12
    return max(0, min(normalized_hour, 23))


def _extract_explicit_hour_minute(question: str, period: Optional[str]) -> Optional[tuple[int, int]]:
    # Examples: 14:30, 14点, 14点30, 3点半
    match = re.search(r"(?<!\d)(\d{1,2})\s*(?:点|:|：)\s*(\d{1,2})?\s*(半)?", question)
    if not match:
        return None
    hour = int(match.group(1))
    if hour > 23:
        return None
    minute = 30 if match.group(3) else int(match.group(2) or 0)
    minute = max(0, min(minute, 59))
    return _normalize_hour(period, hour), minute


def _resolve_relative_date(question: str, now: datetime) -> Optional[date]:
    if "大后天" in question:
        return (now + timedelta(days=3)).date()
    if "后天" in question:
        return (now + timedelta(days=2)).date()
    if "明天" in question:
        return (now + timedelta(days=1)).date()
    if "今天" in question:
        return now.date()

    weekday_match = re.search(r"(下周|本周|这周|周|星期)([一二三四五六日天])", question)
    if not weekday_match:
        return None

    prefix = weekday_match.group(1)
    target_weekday = _WEEKDAY_MAP[weekday_match.group(2)]
    today = now.date()
    current_weekday = today.weekday()

    if prefix == "下周":
        start_of_current_week = today - timedelta(days=current_weekday)
        start_of_next_week = start_of_current_week + timedelta(days=7)
        return start_of_next_week + timedelta(days=target_weekday)

    delta_days = (target_weekday - current_weekday) % 7
    if prefix in {"本周", "这周"} and delta_days == 0:
        return today
    return today + timedelta(days=delta_days)


def _parse_preferred_start(question: str) -> Optional[datetime]:
    now = datetime.utcnow()
    period = _detect_period(question)
    default_hour = _PERIOD_DEFAULT_HOUR.get(period or "", 14)
    explicit_time = _extract_explicit_hour_minute(question, period)

    # Absolute date first: 2026-04-12 / 2026-04-12 14:30
    absolute_date_match = re.search(r"(\d{4}-\d{2}-\d{2})", question)
    if absolute_date_match:
        target_date = datetime.fromisoformat(absolute_date_match.group(1)).date()
        hour, minute = explicit_time or (default_hour, 0)
        return datetime.combine(target_date, datetime.min.time()).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )

    target_date = _resolve_relative_date(question, now)
    if target_date:
        hour, minute = explicit_time or (default_hour, 0)
        return datetime.combine(target_date, datetime.min.time()).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
    return None


def _parse_project_name(question: str) -> str:
    match = re.search(r"(?:项目|project)[:： ]+([A-Za-z0-9_\-\u4e00-\u9fff]+)", question, re.IGNORECASE)
    return match.group(1) if match else ""


def _intent_match(question: str, keywords: List[str]) -> bool:
    lowered = question.lower()
    normalized = _normalize_text(question)
    for keyword in keywords:
        if keyword.lower() in lowered:
            return True
        normalized_keyword = _normalize_text(keyword)
        if normalized_keyword and normalized_keyword in normalized:
            return True
    return False


def _extract_reference_id(question: str, labels: List[str]) -> Optional[int]:
    label_group = "|".join(re.escape(label) for label in labels)
    patterns = [
        rf"(?:{label_group})\s*#?\s*(\d+)",
        rf"#\s*(\d+)\s*(?:{label_group})?",
        rf"(\d+)\s*号?\s*(?:{label_group})",
    ]
    for pattern in patterns:
        match = re.search(pattern, question, re.IGNORECASE)
        if match:
            return int(match.group(1))

    fallback = re.findall(r"\d+", question)
    if len(fallback) == 1 and any(label in question for label in labels):
        return int(fallback[0])
    return None


def _has_context_reference(question: str, labels: List[str]) -> bool:
    return any(label in question for label in labels) and any(token in question for token in _CONTEXT_REFERENCE_KEYWORDS)


def _is_approve_intent(question: str) -> bool:
    lowered = question.lower()
    normalized = _normalize_text(question)
    has_approval_noun = any(token in lowered for token in ["审批", "申请", "approval"])
    if not has_approval_noun:
        return False
    approve_verbs = ["通过", "批准", "同意", "审核通过", "approve"]
    return any(verb in lowered for verb in approve_verbs) or any(
        _normalize_text(verb) in normalized for verb in approve_verbs
    )


def _is_reject_intent(question: str) -> bool:
    lowered = question.lower()
    normalized = _normalize_text(question)
    has_approval_noun = any(token in lowered for token in ["审批", "申请", "approval"])
    if not has_approval_noun:
        return False
    reject_verbs = ["拒绝", "驳回", "不通过", "退回", "reject"]
    return any(verb in lowered for verb in reject_verbs) or any(
        _normalize_text(verb) in normalized for verb in reject_verbs
    )


def _resolve_pending_approval(db: Session, current_user: User, question: str) -> Optional[ApprovalTask]:
    approval_id = _extract_reference_id(question, ["审批", "申请", "approval"])
    query = db.query(ApprovalTask).filter(ApprovalTask.status == "pending")
    if approval_id is not None:
        return query.filter(ApprovalTask.id == approval_id).first()

    if not _has_context_reference(question, ["审批", "申请"]):
        return None

    return (
        query
        .filter(ApprovalTask.requester_id != current_user.id)
        .order_by(ApprovalTask.created_at.asc())
        .first()
    )


def _resolve_follow_up_task_target(db: Session, current_user: User, question: str) -> Optional[FollowUpTask]:
    task_id = _extract_reference_id(question, ["任务", "task"])
    query = db.query(FollowUpTask)
    if task_id is not None:
        return query.filter(FollowUpTask.id == task_id).first()

    if not _has_context_reference(question, ["任务"]):
        return None

    if not is_teacher_or_admin(current_user):
        query = query.filter(FollowUpTask.assigned_user_id == current_user.id)

    return (
        query
        .filter(FollowUpTask.status.in_(["open", "in_progress"]))
        .order_by(FollowUpTask.due_at.asc(), FollowUpTask.created_at.asc())
        .first()
    )


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


def _build_analysis_steps(
    *,
    intent: str,
    resource: Optional[Resource] = None,
    preferred_start: Optional[datetime] = None,
    duration_minutes: Optional[int] = None,
    note: str = "",
) -> List[str]:
    steps: List[str] = []

    if resource:
        steps.append(f"感知输入：识别到目标资源为「{resource.name}」。")
    else:
        steps.append("感知输入：尚未识别到明确资源实体。")

    if intent == "schedule_recommendation":
        duration_text = duration_minutes if duration_minutes is not None else 120
        steps.append(f"推理规划：围绕 {duration_text} 分钟使用时长计算候选时段并评估冲突/评分。")
        if preferred_start:
            steps.append(f"偏好约束：优先靠近你给出的时间点 {preferred_start.strftime('%Y-%m-%d %H:%M')}。")
        steps.append("执行输出：返回可执行时段、首选开始时间和选择理由。")
    elif intent == "inventory_status":
        steps.append("推理规划：读取库存与阈值状态，并判断是否处于紧张区间。")
        steps.append("执行输出：返回当前可用量、总量和状态。")
    elif intent == "approval_status":
        steps.append("推理规划：聚合审批队列的待审、通过、拒绝数量。")
        steps.append("执行输出：返回审批吞吐概况，支持决策优先级。")
    elif intent in {"governance_recommendation", "anomaly_analysis", "follow_up_tasks"}:
        steps.append("推理规划：融合实时业务数据生成治理和闭环建议。")
        steps.append("执行输出：返回可落地动作和优先级提示。")
    else:
        steps.append("推理规划：执行通用业务意图识别并调用对应规则。")
        steps.append("执行输出：给出可执行下一步建议。")

    if note:
        steps.append(f"补充说明：{note}")
    return steps


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
        f"补充：当前待审批 {pending_approvals} 条，可优先处理设备借用审批以提升周转效率。\n"
        "如需落地治理动作，你可以直接说“按建议补货”或“生成补货审批单”。"
    )


def _pick_replenishment_candidate(db: Session, preferred_resource: Optional[Resource] = None) -> Optional[Dict[str, Any]]:
    if preferred_resource and preferred_resource.category == "material" and preferred_resource.status != "disabled":
        shortage = max((preferred_resource.min_threshold or 0) - (preferred_resource.available_count or 0), 0)
        quantity = max(shortage + max(preferred_resource.min_threshold or 1, 1), 5)
        return {"resource": preferred_resource, "quantity": quantity}

    materials = (
        db.query(Resource)
        .filter(Resource.category == "material", Resource.status != "disabled")
        .all()
    )
    if not materials:
        return None

    def _pressure_score(material: Resource) -> float:
        total = max(material.total_count or 0, 1)
        available = max(material.available_count or 0, 0)
        shortage = max((material.min_threshold or 0) - available, 0)
        scarcity = 1 - (available / total)
        return shortage * 3 + scarcity * 2

    target = sorted(materials, key=_pressure_score, reverse=True)[0]
    shortage = max((target.min_threshold or 0) - (target.available_count or 0), 0)
    quantity = max(shortage + max(target.min_threshold or 1, 1), 5)
    return {"resource": target, "quantity": quantity}


def _build_follow_up_task_summary(db: Session, current_user: Optional[User] = None) -> str:
    query = (
        db.query(FollowUpTask)
        .options(joinedload(FollowUpTask.resource), joinedload(FollowUpTask.assigned_user))
        .filter(FollowUpTask.status.in_(["open", "in_progress"]))
    )
    if current_user and not is_teacher_or_admin(current_user):
        query = query.filter(
            or_(
                FollowUpTask.assigned_user_id == current_user.id,
                FollowUpTask.transaction.has(Transaction.user_id == current_user.id),
            )
        )

    tasks = query.order_by(FollowUpTask.due_at.asc(), FollowUpTask.created_at.asc()).limit(5).all()
    if not tasks:
        return "当前没有未完成的闭环任务。"

    lines = ["当前优先处理的闭环任务："]
    for task in tasks:
        resource_name = task.resource.name if task.resource else f"Resource#{task.resource_id}"
        owner = task.assigned_user.real_name if task.assigned_user else "未指派"
        due_hint = task.due_at.strftime("%Y-%m-%d %H:%M") if task.due_at else "无截止时间"
        lines.append(
            f"- #{task.id} [{task.task_type}] {task.title}（资源：{resource_name}，负责人：{owner}，截止：{due_hint}）"
        )
    lines.append("如需我帮你执行关闭，可说“完成任务 #编号”。")
    return "\n".join(lines)


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
    recent_alerts = (
        db.query(Alert)
        .filter(Alert.status != "resolved")
        .order_by(Alert.created_at.desc())
        .limit(5)
        .all()
    )
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
                "status": alert.status,
                "message": alert.message,
                "created_at": alert.created_at.isoformat(),
            }
            for alert in recent_alerts
        ],
    }


def run_business_query(db: Session, question: str, current_user: Optional[User] = None) -> Dict[str, Any]:
    """Answer a read-only question with deterministic business logic."""
    resource = _find_resource_from_question(db, question)

    if _is_schedule_question(question):
        if not resource:
            return {
                "intent": "schedule_recommendation",
                "answer": "请告诉我具体设备名称（例如 3D打印机、激光切割机、万用表），我再帮你查空档。",
                "analysis_steps": _build_analysis_steps(
                    intent="schedule_recommendation",
                    note="缺少设备名称，先补齐约束再进行排程。",
                ),
            }
        duration_minutes = _parse_duration_minutes(question)
        preferred_start = _parse_preferred_start(question)
        slots = get_optimal_time_slots(db, resource.id, duration_minutes, preferred_start)
        if not slots:
            return {
                "intent": "schedule_recommendation",
                "answer": f"暂时没找到 {resource.name} 的合适空档。你可以换一个日期，或缩短预计使用时长后再试。",
                "analysis_steps": _build_analysis_steps(
                    intent="schedule_recommendation",
                    resource=resource,
                    preferred_start=preferred_start,
                    duration_minutes=duration_minutes,
                    note="候选时段不足，建议换日期或缩短时长。",
                ),
            }
        return {
            "intent": "schedule_recommendation",
            "answer": _format_schedule_reply(resource, slots, preferred_start),
            "analysis_steps": _build_analysis_steps(
                intent="schedule_recommendation",
                resource=resource,
                preferred_start=preferred_start,
                duration_minutes=duration_minutes,
            ),
        }

    if any(keyword in question for keyword in ["审批", "待审", "通过", "拒绝"]):
        pending = db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "pending").scalar() or 0
        approved = db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "approved").scalar() or 0
        rejected = db.query(func.count(ApprovalTask.id)).filter(ApprovalTask.status == "rejected").scalar() or 0
        return {
            "intent": "approval_status",
            "answer": f"当前待审批 {pending} 条，已通过 {approved} 条，已拒绝 {rejected} 条。",
            "analysis_steps": _build_analysis_steps(intent="approval_status"),
        }

    if any(keyword in question for keyword in _GOVERNANCE_KEYWORDS):
        return {
            "intent": "governance_recommendation",
            "answer": _build_governance_suggestions(db),
            "analysis_steps": _build_analysis_steps(intent="governance_recommendation"),
        }

    if any(keyword in question.lower() for keyword in _FOLLOW_UP_QUERY_KEYWORDS):
        return {
            "intent": "follow_up_tasks",
            "answer": _build_follow_up_task_summary(db, current_user),
            "analysis_steps": _build_analysis_steps(intent="follow_up_tasks"),
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
            return {
                "intent": "anomaly_analysis",
                "answer": "当前没有超时未归还记录。",
                "analysis_steps": _build_analysis_steps(intent="anomaly_analysis"),
            }
        lines = ["超时未归还记录："]
        for tx in overdue[:5]:
            resource_name = tx.resource.name if tx.resource else f"Resource#{tx.resource_id}"
            user_name = tx.user.real_name if tx.user else f"User#{tx.user_id}"
            overdue_hours = round((datetime.utcnow() - tx.expected_return_time).total_seconds() / 3600, 1)
            lines.append(f"- {user_name} 占用 {resource_name}，已超时 {overdue_hours} 小时")
        return {
            "intent": "anomaly_analysis",
            "answer": "\n".join(lines),
            "analysis_steps": _build_analysis_steps(intent="anomaly_analysis"),
        }

    if resource:
        item_suffix = ""
        if resource.category == "device":
            tracked_count = len([item for item in resource.items if item.status != "disabled"])
            item_suffix = f"，已建档实例 {tracked_count} 台"
        answer = (
            f"{resource.name} 当前可用 {resource.available_count}/{resource.total_count}"
            f"，阈值 {resource.min_threshold}，状态 {resource.status}{item_suffix}。"
        )
        return {
            "intent": "inventory_status",
            "answer": answer,
            "analysis_steps": _build_analysis_steps(intent="inventory_status", resource=resource),
        }

    low_count = db.query(func.count(Resource.id)).filter(Resource.available_count <= Resource.min_threshold).scalar() or 0
    return {
        "intent": "recommendation",
        "answer": f"当前共有 {low_count} 类资源处于低库存。你可以继续问我库存、审批、排程或异常治理问题。",
        "analysis_steps": _build_analysis_steps(intent="recommendation"),
    }


def build_action_proposal(db: Session, current_user: User, question: str) -> Optional[Dict]:
    """Build a pending tool action if the user is asking for one."""
    resource = _find_resource_from_question(db, question)
    quantity = _parse_quantity(question)
    duration_minutes = _parse_duration_minutes(question)
    preferred_start = _parse_preferred_start(question)
    project_name = _parse_project_name(question)

    governance_follow_up = (
        _intent_match(question, _REPLENISH_APPROVAL_ACTION_KEYWORDS)
        or (
            "建议" in question
            and any(token in question for token in ["执行", "落地", "一键"])
            and any(token in question for token in ["补货", "库存"])
        )
    )
    if governance_follow_up and current_user.role in {"teacher", "admin"}:
        candidate = _pick_replenishment_candidate(db, resource)
        if candidate:
            target = candidate["resource"]
            quantity = int(candidate["quantity"])
            return {
                "name": "create_replenish_approval",
                "title": f"生成补货审批单：{target.name} x{quantity}",
                "proposed_payload": {
                    "resource_id": target.id,
                    "action": "replenish",
                    "quantity": quantity,
                    "purpose": "governance replenishment recommendation",
                    "project_name": project_name,
                    "note": question,
                    "reason": "Agent-generated governance replenishment recommendation",
                },
            }

    if _intent_match(question, _BORROW_ACTION_KEYWORDS) and resource:
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

    if _intent_match(question, _CONSUME_ACTION_KEYWORDS) and resource:
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

    if _intent_match(question, _REPLENISH_ACTION_KEYWORDS) and resource and is_admin(current_user):
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

    if _intent_match(question, _LOSS_ACTION_KEYWORDS) and resource and is_teacher_or_admin(current_user):
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

    if (_intent_match(question, _APPROVE_ACTION_KEYWORDS) or _is_approve_intent(question)) and is_teacher_or_admin(current_user):
        approval = _resolve_pending_approval(db, current_user, question)
        if approval:
            return {
                "name": "approve_task",
                "title": f"通过审批 #{approval.id}",
                "proposed_payload": {"approval_id": approval.id, "reason": question},
            }

    if (_intent_match(question, _REJECT_ACTION_KEYWORDS) or _is_reject_intent(question)) and is_teacher_or_admin(current_user):
        approval = _resolve_pending_approval(db, current_user, question)
        if approval:
            return {
                "name": "reject_task",
                "title": f"拒绝审批 #{approval.id}",
                "proposed_payload": {"approval_id": approval.id, "reason": question},
            }

    if _intent_match(question, _TASK_DONE_KEYWORDS):
        follow_up = _resolve_follow_up_task_target(db, current_user, question)
        if follow_up:
            can_update = is_teacher_or_admin(current_user) or follow_up.assigned_user_id == current_user.id
            if can_update:
                return {
                    "name": "update_follow_up_task",
                    "title": f"将闭环任务 #{follow_up.id} 标记为完成",
                    "proposed_payload": {"task_id": follow_up.id, "status": "done", "note": question},
                }

    if _intent_match(question, _TASK_PROGRESS_KEYWORDS):
        follow_up = _resolve_follow_up_task_target(db, current_user, question)
        if follow_up:
            can_update = is_teacher_or_admin(current_user) or follow_up.assigned_user_id == current_user.id
            if can_update:
                return {
                    "name": "update_follow_up_task",
                    "title": f"将闭环任务 #{follow_up.id} 标记为处理中",
                    "proposed_payload": {"task_id": follow_up.id, "status": "in_progress", "note": question},
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
    if resource.status == "disabled":
        raise ValueError("Resource is archived/disabled and cannot be used")

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
        borrow_time=to_utc_naive(datetime.fromisoformat(payload["borrow_time"])) if payload.get("borrow_time") else None,
        expected_return_time=(
            to_utc_naive(datetime.fromisoformat(payload["expected_return_time"]))
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
            conflicts = check_time_slot_conflict(
                db,
                resource.id,
                tx.borrow_time,
                tx.expected_return_time,
                requested_quantity=quantity,
                capacity=resource.total_count,
            )
            if conflicts:
                raise ValueError("Requested time slot exceeds available device capacity")
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


def _execute_follow_up_task_tool(db: Session, current_user: User, payload: Dict) -> Dict:
    task_id = int(payload["task_id"])
    target_status = payload.get("status", "done")
    if target_status not in {"open", "in_progress", "done", "cancelled"}:
        raise ValueError("Unsupported follow-up task status")

    task = db.query(FollowUpTask).filter(FollowUpTask.id == task_id).first()
    if not task:
        raise ValueError("Follow-up task not found")

    can_update = is_teacher_or_admin(current_user) or task.assigned_user_id == current_user.id
    if not can_update:
        raise ValueError("You cannot update this follow-up task")

    previous_status = task.status
    task.status = target_status
    now = datetime.utcnow()
    task.updated_at = now
    note = (payload.get("note") or "").strip()
    if note:
        actor = current_user.real_name or current_user.username
        task.description = append_note(task.description, f"[{now.isoformat()}] {actor}: {note}")

    if payload.get("result") is not None:
        task.result = (payload.get("result") or "").strip()
    if payload.get("outcome_score") is not None:
        task.outcome_score = float(payload.get("outcome_score"))

    if target_status in {"done", "cancelled"}:
        task.closed_at = now
        if not (task.result or "").strip() and note:
            task.result = note
        if task.outcome_score is None:
            task.outcome_score = 100.0 if target_status == "done" else 60.0
    elif previous_status in {"done", "cancelled"}:
        task.closed_at = None

    db.add(task)
    db.commit()
    db.refresh(task)
    return {"summary": f"已将闭环任务 #{task.id} 更新为 {task.status}。"}


def _execute_replenish_approval_tool(db: Session, current_user: User, payload: Dict) -> Dict:
    if current_user.role not in {"teacher", "admin"}:
        raise ValueError("Only teachers or admins can create replenishment approvals")

    resource_id = int(payload["resource_id"])
    quantity = int(payload.get("quantity", 1))
    if quantity <= 0:
        raise ValueError("Replenishment quantity must be positive")

    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource:
        raise ValueError("Resource not found")
    if resource.status == "disabled":
        raise ValueError("Resource is archived/disabled and cannot be used")

    tx = Transaction(
        resource_id=resource.id,
        user_id=current_user.id,
        action="replenish",
        quantity=quantity,
        note=payload.get("note", ""),
        purpose=payload.get("purpose", "governance replenishment recommendation"),
        project_name=payload.get("project_name", ""),
        estimated_quantity=quantity,
        status="pending",
        is_approved=False,
        inventory_applied=False,
    )
    db.add(tx)
    db.flush()
    tx.resource = resource
    tx.user = current_user
    approval = create_approval_task(
        db,
        tx,
        current_user,
        reason=payload.get("reason", "Agent-generated replenishment recommendation"),
    )
    db.commit()
    db.refresh(tx)
    return {
        "summary": f"已生成补货审批单 #{approval.id}（流水 #{tx.id}），等待审批后执行入库。",
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
    elif tool_name == "create_replenish_approval":
        result = _execute_replenish_approval_tool(db, current_user, payload)
    elif tool_name == "update_follow_up_task":
        result = _execute_follow_up_task_tool(db, current_user, payload)
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
