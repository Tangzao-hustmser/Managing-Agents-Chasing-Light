"""Alert emission helpers with deduplication and state migration."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Alert


def emit_alert(
    db: Session,
    *,
    level: str,
    alert_type: str,
    message: str,
    dedup_key: str = "",
    dedup_window_seconds: Optional[int] = None,
    reopen_resolved: bool = False,
) -> Alert:
    """Emit one alert with dedup and state migration support."""
    now = datetime.utcnow()
    window_seconds = int(dedup_window_seconds or settings.alert_dedup_window_seconds or 300)
    window_start = now - timedelta(seconds=max(window_seconds, 0))
    resolved_dedup_key = (dedup_key or f"{alert_type}:{message[:80]}").strip()

    recent = (
        db.query(Alert)
        .filter(Alert.type == alert_type, Alert.dedup_key == resolved_dedup_key)
        .order_by(Alert.created_at.desc())
        .first()
    )

    if recent and recent.status != "resolved" and (recent.last_seen_at or recent.created_at) >= window_start:
        recent.last_seen_at = now
        recent.occurrence_count = int(recent.occurrence_count or 1) + 1
        recent.level = level
        recent.message = message
        if recent.status == "acknowledged":
            recent.status = "open"
        db.add(recent)
        return recent

    if recent and recent.status == "resolved" and reopen_resolved:
        recent.status = "open"
        recent.level = level
        recent.message = message
        recent.last_seen_at = now
        recent.occurrence_count = int(recent.occurrence_count or 0) + 1
        db.add(recent)
        return recent

    created = Alert(
        level=level,
        type=alert_type,
        message=message,
        status="open",
        dedup_key=resolved_dedup_key,
        last_seen_at=now,
        occurrence_count=1,
    )
    db.add(created)
    return created


def resolve_alert_by_dedup_key(db: Session, *, alert_type: str, dedup_key: str) -> None:
    """Resolve matching open alerts by dedup key."""
    alerts = (
        db.query(Alert)
        .filter(
            Alert.type == alert_type,
            Alert.dedup_key == dedup_key,
            Alert.status != "resolved",
        )
        .all()
    )
    if not alerts:
        return
    now = datetime.utcnow()
    for alert in alerts:
        alert.status = "resolved"
        alert.resolved_at = now
        alert.resolution_note = "auto-resolved by rule state migration"
        db.add(alert)
