"""Notification delivery log routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import NotificationDelivery, User
from app.routers.auth import get_current_user
from app.schemas import NotificationDeliveryOut
from app.services.auth_service import is_teacher_or_admin

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/deliveries", response_model=list[NotificationDeliveryOut])
def list_notification_deliveries(
    event_type: str = Query(default="", description="optional event_type filter"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List notification delivery logs. Teacher/admin only."""
    if not is_teacher_or_admin(current_user):
        raise HTTPException(status_code=403, detail="Only teachers or admins can view notification logs")

    query = db.query(NotificationDelivery)
    if event_type:
        query = query.filter(NotificationDelivery.event_type == event_type)
    return query.order_by(NotificationDelivery.created_at.desc()).limit(limit).all()
