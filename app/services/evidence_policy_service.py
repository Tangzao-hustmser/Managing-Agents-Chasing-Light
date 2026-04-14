"""Evidence policy helpers for high-risk actions and inventory audits."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import FollowUpTask, Resource, Transaction
from app.services.alert_service import emit_alert
from app.services.notification_service import dispatch_notification_event

VALID_EVIDENCE_TYPES = {"image", "video", "document", "text", "audio"}


def is_evidence_complete(evidence_url: str = "", evidence_type: str = "") -> bool:
    """Return True when evidence has minimum required fields."""
    normalized_type = (evidence_type or "").strip().lower()
    normalized_url = (evidence_url or "").strip()
    return bool(normalized_url and normalized_type in VALID_EVIDENCE_TYPES)


def ensure_evidence_backfill_task(
    db: Session,
    *,
    resource: Resource,
    transaction: Optional[Transaction],
    evidence_url: str,
    evidence_type: str,
    scenario: str,
    assigned_user_id: Optional[int] = None,
    due_days: int = 2,
) -> bool:
    """Create a deduplicated evidence-backfill task if evidence is incomplete."""
    if is_evidence_complete(evidence_url, evidence_type):
        return False

    transaction_id = transaction.id if transaction else None
    existing = (
        db.query(FollowUpTask)
        .filter(
            FollowUpTask.task_type == "evidence_backfill",
            FollowUpTask.resource_id == resource.id,
            FollowUpTask.transaction_id == transaction_id,
            FollowUpTask.status.in_(["open", "in_progress"]),
        )
        .first()
    )
    if existing:
        return True

    missing_fields = []
    if not (evidence_url or "").strip():
        missing_fields.append("evidence_url")
    normalized_type = (evidence_type or "").strip().lower()
    if normalized_type not in VALID_EVIDENCE_TYPES:
        missing_fields.append("evidence_type")

    marker = f"scenario={scenario}, tx={transaction_id or 'none'}"
    task = FollowUpTask(
        transaction_id=transaction_id,
        resource_id=resource.id,
        assigned_user_id=assigned_user_id,
        task_type="evidence_backfill",
        status="open",
        title=f"补齐{scenario}证据（{resource.name}）",
        description=(
            f"高风险操作缺少完整证据，需补齐字段：{', '.join(missing_fields) or 'evidence_url,evidence_type'}。"
            f" {marker}"
        ),
        due_at=datetime.utcnow() + timedelta(days=due_days),
    )
    db.add(task)
    db.flush()

    _upsert_evidence_alert(db, task, scenario)
    dispatch_notification_event(
        db,
        event_type="evidence_backfill_required",
        title="补证任务提醒",
        content=f"任务 #{task.id} 需要补齐{scenario}证据（资源 {resource.name}）。",
        correlation_key=f"evidence_task:{task.id}",
    )
    return True


def _upsert_evidence_alert(db: Session, task: FollowUpTask, scenario: str) -> None:
    message = (
        f"Missing evidence for {scenario}: task#{task.id}, resource={task.resource_id}, "
        f"transaction={task.transaction_id or 'none'}."
    )
    emit_alert(
        db,
        level="warn",
        alert_type="evidence_missing",
        message=message,
        dedup_key=f"evidence_missing:task:{task.id}",
        reopen_resolved=True,
    )
