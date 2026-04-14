"""Alert routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Alert, User
from app.routers.auth import get_current_user
from app.schemas import AlertActionIn, AlertOut, MessageOut
from app.services.auth_service import is_teacher_or_admin
from app.services.audit_service import write_audit_log
from app.services.rate_limit_service import RateLimitExceededError, enforce_write_rate_limit

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _enforce_write_limit(user_id: int, endpoint_key: str) -> None:
    try:
        enforce_write_rate_limit(user_id=user_id, endpoint_key=endpoint_key)
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=429,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc


@router.get("", response_model=list[AlertOut])
def list_alerts(
    include_resolved: bool = Query(default=False, description="Whether to include resolved alerts"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return latest alerts for authenticated users."""
    query = db.query(Alert)
    if not include_resolved:
        query = query.filter(Alert.status != "resolved")
    return query.order_by(Alert.created_at.desc()).all()


@router.post("/{alert_id}/acknowledge", response_model=AlertOut)
def acknowledge_alert(
    alert_id: int,
    payload: AlertActionIn,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Acknowledge one alert. Teacher/admin only."""
    if not is_teacher_or_admin(current_user):
        raise HTTPException(status_code=403, detail="Only teachers or admins can acknowledge alerts")
    _enforce_write_limit(current_user.id, "alerts.acknowledge")
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status == "resolved":
        raise HTTPException(status_code=400, detail="Resolved alert cannot be acknowledged again")

    alert.status = "acknowledged"
    alert.acknowledged_at = datetime.utcnow()
    alert.acknowledged_by_user_id = current_user.id
    note = payload.note.strip()
    if note:
        alert.resolution_note = note
    db.add(alert)
    write_audit_log(
        db,
        actor=current_user,
        action="alert.acknowledge",
        entity_type="alert",
        entity_id=alert.id,
        detail={"note": note, "status": alert.status},
        request=request,
    )
    db.commit()
    db.refresh(alert)
    return alert


@router.post("/{alert_id}/resolve", response_model=MessageOut)
def resolve_alert(
    alert_id: int,
    payload: AlertActionIn,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Resolve/clear one alert. Teacher/admin only."""
    if not is_teacher_or_admin(current_user):
        raise HTTPException(status_code=403, detail="Only teachers or admins can resolve alerts")
    _enforce_write_limit(current_user.id, "alerts.resolve")
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.status = "resolved"
    alert.resolved_at = datetime.utcnow()
    alert.resolved_by_user_id = current_user.id
    note = payload.note.strip()
    if note:
        alert.resolution_note = note
    db.add(alert)
    write_audit_log(
        db,
        actor=current_user,
        action="alert.resolve",
        entity_type="alert",
        entity_id=alert.id,
        detail={"note": note, "status": alert.status},
        request=request,
    )
    db.commit()
    return MessageOut(message="Alert resolved")
