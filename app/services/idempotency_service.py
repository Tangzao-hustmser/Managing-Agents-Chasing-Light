"""Idempotency key helpers for write endpoints."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import IdempotencyRequest


class IdempotencyConflictError(ValueError):
    """Raised when one key is reused with a different payload."""


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default)


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _normalize_key(raw_key: Optional[str]) -> str:
    return (raw_key or "").strip()


@dataclass
class IdempotencyContext:
    """Runtime context returned by ``prepare_idempotency``."""

    enabled: bool = False
    scope: str = ""
    user_id: int = 0
    key: str = ""
    request_hash: str = ""
    entity_key: str = ""
    cached_response: Optional[dict] = None


def prepare_idempotency(
    db: Session,
    *,
    scope: str,
    user_id: int,
    idempotency_key: Optional[str],
    request_payload: Any,
    entity_key: str = "",
) -> IdempotencyContext:
    """Load a previously successful response for the same key, if it exists."""
    key = _normalize_key(idempotency_key)
    if not key:
        return IdempotencyContext()
    if len(key) > 128:
        raise IdempotencyConflictError("Idempotency-Key is too long (max 128 chars)")

    request_hash = _hash_payload(request_payload)
    row = (
        db.query(IdempotencyRequest)
        .filter(
            IdempotencyRequest.scope == scope,
            IdempotencyRequest.user_id == user_id,
            IdempotencyRequest.idempotency_key == key,
        )
        .first()
    )
    if row:
        if row.request_hash != request_hash:
            raise IdempotencyConflictError("Idempotency-Key has already been used with a different payload")
        if row.status == "succeeded" and row.response_body:
            try:
                return IdempotencyContext(
                    enabled=True,
                    scope=scope,
                    user_id=user_id,
                    key=key,
                    request_hash=request_hash,
                    entity_key=entity_key or row.entity_key or "",
                    cached_response=json.loads(row.response_body),
                )
            except json.JSONDecodeError:
                # Fallback to recompute; do not fail the request because of one bad cached row.
                pass

    return IdempotencyContext(
        enabled=True,
        scope=scope,
        user_id=user_id,
        key=key,
        request_hash=request_hash,
        entity_key=entity_key,
    )


def persist_idempotent_response(
    db: Session,
    *,
    context: IdempotencyContext,
    response_payload: Any,
    status_code: int = 200,
) -> None:
    """Store successful response payload for future replay."""
    if not context.enabled:
        return

    response_body = _canonical_json(response_payload)
    row = (
        db.query(IdempotencyRequest)
        .filter(
            IdempotencyRequest.scope == context.scope,
            IdempotencyRequest.user_id == context.user_id,
            IdempotencyRequest.idempotency_key == context.key,
        )
        .first()
    )

    if row is None:
        row = IdempotencyRequest(
            scope=context.scope,
            user_id=context.user_id,
            idempotency_key=context.key,
            request_hash=context.request_hash,
        )
        db.add(row)

    if row.request_hash != context.request_hash:
        raise IdempotencyConflictError("Idempotency-Key has already been used with a different payload")

    row.entity_key = context.entity_key
    row.status = "succeeded"
    row.response_code = status_code
    row.response_body = response_body
    row.updated_at = datetime.utcnow()
