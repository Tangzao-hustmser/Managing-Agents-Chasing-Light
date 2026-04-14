"""Operational audit logging helpers."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog, User


def _dump_detail(detail: Optional[Dict[str, Any]]) -> str:
    if not detail:
        return "{}"
    try:
        return json.dumps(detail, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return "{}"


def write_audit_log(
    db: Session,
    *,
    actor: User,
    action: str,
    entity_type: str = "",
    entity_id: Any = "",
    detail: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
    idempotency_key: str = "",
) -> None:
    """Append one audit record without committing."""
    db.add(
        AuditLog(
            actor_user_id=actor.id,
            actor_role=actor.role or "",
            action=action,
            entity_type=entity_type or "",
            entity_id=str(entity_id) if entity_id is not None else "",
            http_method=request.method if request else "",
            request_path=request.url.path if request else "",
            idempotency_key=(idempotency_key or "").strip(),
            detail_json=_dump_detail(detail),
        )
    )
