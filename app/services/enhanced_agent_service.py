"""Enhanced agent service wrapper."""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Alert, ApprovalTask, FollowUpTask, Transaction, User
from app.services.advanced_analytics import AdvancedAnalytics
from app.services.agent_tool_service import get_real_time_data_context
from app.services.llm_service import chat_with_agent


def _scheduler_agent_trace(db: Session, question: str) -> Dict:
    pending_borrow = (
        db.query(func.count(ApprovalTask.id))
        .join(Transaction, ApprovalTask.transaction_id == Transaction.id)
        .filter(ApprovalTask.status == "pending", Transaction.action == "borrow")
        .scalar()
        or 0
    )
    active_borrow = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.action == "borrow", Transaction.status == "approved", Transaction.return_time.is_(None))
        .scalar()
        or 0
    )
    next_week = datetime.utcnow() + timedelta(days=7)
    upcoming_borrow = (
        db.query(func.count(Transaction.id))
        .filter(
            Transaction.action == "borrow",
            Transaction.status.in_(["pending", "approved"]),
            Transaction.borrow_time.isnot(None),
            Transaction.borrow_time <= next_week,
        )
        .scalar()
        or 0
    )
    focus = "capacity_and_slot_balancing"
    if any(token in question for token in ["排程", "空档", "预约", "时段"]):
        focus = "schedule_request_resolution"
    findings = [
        f"待审批借用 {pending_borrow} 条",
        f"当前在借中设备记录 {active_borrow} 条",
        f"未来7天内借用需求 {upcoming_borrow} 条",
    ]
    recommendation = "优先错峰分配并结合公平策略降权高频占用用户。"
    return {
        "agent": "scheduler_agent",
        "objective": focus,
        "key_findings": findings,
        "recommended_action": recommendation,
        "confidence": 0.84,
    }


def _governance_agent_trace(db: Session) -> Dict:
    open_tasks = (
        db.query(func.count(FollowUpTask.id))
        .filter(FollowUpTask.status.in_(["open", "in_progress"]))
        .scalar()
        or 0
    )
    overdue_borrow = (
        db.query(func.count(Transaction.id))
        .filter(
            Transaction.action == "borrow",
            Transaction.status == "approved",
            Transaction.return_time.is_(None),
            Transaction.expected_return_time.isnot(None),
            Transaction.expected_return_time < datetime.utcnow(),
        )
        .scalar()
        or 0
    )
    fairness_index = 1.0
    try:
        analytics = AdvancedAnalytics(db).get_comprehensive_analytics(days=30)
        fairness_index = float(analytics.get("fairness_metrics", {}).get("fairness_index", 1.0))
    except Exception:
        fairness_index = 1.0

    findings = [
        f"开放闭环任务 {open_tasks} 条",
        f"超时未归还 {overdue_borrow} 条",
        f"公平指数 {fairness_index:.2f}",
    ]
    recommendation = "将高风险异常优先转闭环动作，并持续追踪公平指数变化。"
    return {
        "agent": "governance_agent",
        "objective": "risk_and_policy_governance",
        "key_findings": findings,
        "recommended_action": recommendation,
        "confidence": 0.81,
    }


def _evidence_agent_trace(db: Session) -> Dict:
    open_evidence_tasks = (
        db.query(func.count(FollowUpTask.id))
        .filter(FollowUpTask.task_type == "evidence_backfill", FollowUpTask.status.in_(["open", "in_progress"]))
        .scalar()
        or 0
    )
    unresolved_evidence_alerts = (
        db.query(func.count(Alert.id))
        .filter(Alert.type == "evidence_missing", Alert.status != "resolved")
        .scalar()
        or 0
    )
    loss_or_damage_events = (
        db.query(func.count(Transaction.id))
        .filter(
            Transaction.action.in_(["lost", "borrow"]),
            Transaction.status.in_(["approved", "returned"]),
            (
                (Transaction.action == "lost")
                | (Transaction.condition_return.in_(["damaged", "partial_lost"]))
            ),
        )
        .scalar()
        or 0
    )
    findings = [
        f"补证任务 {open_evidence_tasks} 条",
        f"证据缺失预警 {unresolved_evidence_alerts} 条",
        f"高风险借还事件 {loss_or_damage_events} 条",
    ]
    recommendation = "优先清理补证任务，确保异常处置均可追溯。"
    return {
        "agent": "evidence_agent",
        "objective": "evidence_integrity_and_traceability",
        "key_findings": findings,
        "recommended_action": recommendation,
        "confidence": 0.86,
    }


def _build_multi_agent_trace(db: Session, question: str) -> List[Dict]:
    return [
        _scheduler_agent_trace(db, question),
        _governance_agent_trace(db),
        _evidence_agent_trace(db),
    ]


def _build_orchestration_summary(trace: List[Dict]) -> str:
    if not trace:
        return "协作代理未返回结果。"
    top_risk = next((item for item in trace if item["agent"] == "governance_agent"), trace[0])
    top_action = top_risk.get("recommended_action", "")
    return (
        "多代理协作完成：调度代理评估容量与排程，治理代理评估风险与公平，证据代理评估可追溯性。"
        f"当前优先建议：{top_action}"
    )


def enhanced_ask_agent(
    db: Session,
    current_user: User,
    question: str,
    session_id: Optional[str] = None,
    *,
    confirm: bool = False,
    confirmation_token: Optional[str] = None,
    llm_options: Optional[Dict] = None,
) -> Dict:
    """Return enhanced agent output with real-time context."""
    result = chat_with_agent(
        db,
        current_user,
        question,
        session_id=session_id,
        confirm=confirm,
        confirmation_token=confirmation_token,
        llm_options=llm_options,
    )
    trace = _build_multi_agent_trace(db, question)
    return {
        "session_id": result["session_id"],
        "answer": result["reply"],
        "success": True,
        "analysis_steps": result.get("analysis_steps", []),
        "real_time_data": get_real_time_data_context(db),
        "multi_agent_trace": trace,
        "orchestration_summary": _build_orchestration_summary(trace),
        "confirmation_required": result.get("confirmation_required", False),
        "pending_action": result.get("pending_action"),
        "executed_tools": result.get("executed_tools", []),
    }
