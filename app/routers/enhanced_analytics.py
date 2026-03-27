"""Enhanced analytics routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.routers.auth import get_current_user
from app.schemas import AnalyticsResponse, DemandPredictionResponse
from app.services.advanced_analytics import get_comprehensive_analytics, predict_future_demand

router = APIRouter(prefix="/enhanced-analytics", tags=["enhanced-analytics"])


@router.get("/comprehensive", response_model=AnalyticsResponse)
def get_comprehensive_analytics_endpoint(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the enhanced analytics report. Admin only."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can access enhanced analytics")
    try:
        return AnalyticsResponse(**get_comprehensive_analytics(db=db, days=days))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Enhanced analytics error: {exc}") from exc


@router.get("/demand-prediction/{resource_id}", response_model=DemandPredictionResponse)
def get_demand_prediction_endpoint(
    resource_id: int,
    days_ahead: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return enhanced demand prediction. Admin only."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can access demand prediction")
    try:
        return DemandPredictionResponse(**predict_future_demand(db=db, resource_id=resource_id, days_ahead=days_ahead))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Demand prediction error: {exc}") from exc


@router.get("/health")
def enhanced_analytics_health_check():
    """Health check for enhanced analytics."""
    return {
        "service": "enhanced_analytics",
        "status": "running",
        "features": [
            "comprehensive_analytics",
            "demand_prediction",
            "fairness_metrics",
            "anomaly_scores",
        ],
    }
