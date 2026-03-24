"""预警查询路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Alert
from app.schemas import AlertOut

router = APIRouter(prefix="/alerts", tags=["风险预警"])


@router.get("", response_model=list[AlertOut])
def list_alerts(db: Session = Depends(get_db)):
    """返回最新预警，默认按时间倒序。"""
    return db.query(Alert).order_by(Alert.created_at.desc()).all()
