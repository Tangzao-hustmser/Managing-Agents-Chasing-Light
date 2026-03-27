"""Alert routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Alert, User
from app.routers.auth import get_current_user
from app.schemas import AlertOut

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
def list_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return latest alerts for authenticated users."""
    return db.query(Alert).order_by(Alert.created_at.desc()).all()
