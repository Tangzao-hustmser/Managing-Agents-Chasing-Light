"""Follow-up task audit and SLA helpers."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import FollowUpTask
from app.services.alert_service import emit_alert
from app.services.notification_service import dispatch_notification_event

_SLA_DEFAULT_HOURS = {
    "open": 24,
    "in_progress": 12,
}


def compute_sla_status(task: FollowUpTask, now: Optional[datetime] = None) -> str:
    """Return on_track/overdue/closed SLA status."""
    now = now or datetime.utcnow()
    if task.status in {"done", "cancelled"}:
        return "closed"
    deadline = task.due_at
    if deadline is None:
        base_time = task.updated_at or task.created_at or now
        deadline = base_time + timedelta(hours=_SLA_DEFAULT_HOURS.get(task.status, 24))
    return "overdue" if deadline < now else "on_track"


def apply_follow_up_sla(db: Session, now: Optional[datetime] = None) -> int:
    """Escalate overdue open/in_progress tasks and raise deduplicated alerts."""
    now = now or datetime.utcnow()
    tasks = (
        db.query(FollowUpTask)
        .filter(FollowUpTask.status.in_(["open", "in_progress"]))
        .all()
    )
    escalated = 0
    for task in tasks:
        if compute_sla_status(task, now) != "overdue":
            continue
        if task.escalation_level > 0 and task.escalated_at is not None:
            continue

        task.escalation_level = max(int(task.escalation_level or 0), 1)
        task.escalated_at = now
        task.updated_at = now
        db.add(task)
        _upsert_overdue_alert(db, task, now)
        escalated += 1
    return escalated


def _upsert_overdue_alert(db: Session, task: FollowUpTask, now: datetime) -> None:
    due_hint = task.due_at.strftime("%Y-%m-%d %H:%M") if task.due_at else "auto SLA window"
    message = (
        f"Follow-up task#{task.id} ({task.title}) is overdue under SLA. "
        f"status={task.status}, due={due_hint}, escalated_at={now.isoformat()}."
    )
    emit_alert(
        db,
        level="error" if task.status == "open" else "warn",
        alert_type="follow_up_sla_overdue",
        message=message,
        dedup_key=f"follow_up_sla_overdue:task:{task.id}",
        reopen_resolved=True,
    )
    dispatch_notification_event(
        db,
        event_type="follow_up_sla_overdue",
        title="超期任务升级提醒",
        content=f"闭环任务 #{task.id} 已超期升级，请优先处理。",
        correlation_key=f"follow_up_task:{task.id}",
    )
