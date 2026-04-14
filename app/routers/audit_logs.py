"""Audit log routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuditLog, User
from app.routers.auth import get_current_user
from app.schemas import AuditLogOut
from app.services.auth_service import is_teacher_or_admin

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("", response_model=list[AuditLogOut])
def list_audit_logs(
    action: str = Query(default="", description="optional action filter"),
    entity_type: str = Query(default="", description="optional entity_type filter"),
    actor_user_id: int = Query(default=0, ge=0, description="optional actor user id filter"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List key operation audit logs. Teacher/admin only."""
    if not is_teacher_or_admin(current_user):
        raise HTTPException(status_code=403, detail="Only teachers or admins can view audit logs")

    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if actor_user_id:
        query = query.filter(AuditLog.actor_user_id == actor_user_id)
    return query.order_by(AuditLog.created_at.desc()).limit(limit).all()
