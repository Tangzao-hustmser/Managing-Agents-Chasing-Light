"""Notification dispatch and delivery logs."""

from __future__ import annotations

from datetime import datetime
from typing import Dict

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import NotificationDelivery


def dispatch_notification_event(
    db: Session,
    *,
    event_type: str,
    title: str,
    content: str,
    correlation_key: str = "",
) -> Dict[str, int]:
    """Dispatch a notification event to enabled channels and write delivery logs."""
    sent = 0
    failed = 0

    if settings.notify_in_app_enabled:
        db.add(
            NotificationDelivery(
                event_type=event_type,
                channel="in_app",
                title=title,
                content=content,
                target="dashboard",
                correlation_key=correlation_key,
                status="sent",
                response_message="stored as in-app notification log",
            )
        )
        sent += 1
    else:
        db.add(
            NotificationDelivery(
                event_type=event_type,
                channel="in_app",
                title=title,
                content=content,
                target="dashboard",
                correlation_key=correlation_key,
                status="skipped",
                response_message="notify_in_app_enabled=false",
            )
        )

    if settings.notify_webhook_enabled:
        target = (settings.notify_webhook_url or "").strip()
        if not target:
            db.add(
                NotificationDelivery(
                    event_type=event_type,
                    channel="webhook",
                    title=title,
                    content=content,
                    target=target,
                    correlation_key=correlation_key,
                    status="failed",
                    response_message="notify_webhook_enabled=true but notify_webhook_url is empty",
                )
            )
            failed += 1
        else:
            payload = {
                "event_type": event_type,
                "title": title,
                "content": content,
                "correlation_key": correlation_key,
                "timestamp": datetime.utcnow().isoformat(),
            }
            try:
                with httpx.Client(timeout=max(int(settings.notify_timeout), 3)) as client:
                    response = client.post(target, json=payload)
                status = "sent" if 200 <= response.status_code < 300 else "failed"
                if status == "sent":
                    sent += 1
                else:
                    failed += 1
                db.add(
                    NotificationDelivery(
                        event_type=event_type,
                        channel="webhook",
                        title=title,
                        content=content,
                        target=target,
                        correlation_key=correlation_key,
                        status=status,
                        response_message=f"http {response.status_code}",
                    )
                )
            except Exception as exc:
                failed += 1
                db.add(
                    NotificationDelivery(
                        event_type=event_type,
                        channel="webhook",
                        title=title,
                        content=content,
                        target=target,
                        correlation_key=correlation_key,
                        status="failed",
                        response_message=str(exc),
                    )
                )

    return {"sent": sent, "failed": failed}
