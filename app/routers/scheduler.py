"""Smart scheduling routes."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.routers.auth import get_current_user
from app.schemas import DemandPredictionResponse, OptimizationResponse, SchedulerRequest, SchedulerResponse
from app.services.smart_scheduler import get_optimal_time_slots, optimize_resource_allocation, predict_resource_demand

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.post("/optimal-slots", response_model=SchedulerResponse)
def get_optimal_slots(
    payload: SchedulerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return recommended time slots."""
    try:
        slots = get_optimal_time_slots(
            db=db,
            resource_id=payload.resource_id,
            duration_minutes=payload.duration_minutes,
            preferred_start=payload.preferred_start,
        )
        return SchedulerResponse(
            resource_id=payload.resource_id,
            duration_minutes=payload.duration_minutes,
            optimal_slots=slots,
            generated_at=datetime.utcnow(),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Scheduling error: {exc}") from exc


@router.get("/demand-prediction/{resource_id}", response_model=DemandPredictionResponse)
def get_demand_prediction(
    resource_id: int,
    days_ahead: Optional[int] = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return scheduler demand prediction."""
    try:
        predictions = predict_resource_demand(
            db=db,
            resource_id=resource_id,
            days_ahead=days_ahead,
        )
        return DemandPredictionResponse(
            resource_id=resource_id,
            days_ahead=days_ahead or 7,
            predictions=predictions,
            generated_at=datetime.utcnow(),
            prediction_method="scheduler_heuristic",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Demand prediction error: {exc}") from exc


@router.get("/optimize-allocation", response_model=OptimizationResponse)
def optimize_allocation(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return allocation recommendations. Admin only."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can optimize allocation")
    try:
        optimization_result = optimize_resource_allocation(db=db)
        return OptimizationResponse(
            total_devices=optimization_result["total_devices"],
            recommendations=optimization_result["recommendations"],
            generated_at=optimization_result["generated_at"],
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Allocation optimization error: {exc}") from exc


@router.get("/health")
def scheduler_health_check():
    """Health check for the scheduler."""
    return {
        "service": "smart_scheduler",
        "status": "running",
        "features": [
            "optimal_time_slots",
            "demand_prediction",
            "resource_optimization",
        ],
    }
