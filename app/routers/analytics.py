"""Basic dashboard analytics routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Alert, Resource, Transaction, User
from app.routers.auth import get_current_user
from app.schemas import KPIDashboardResponse
from app.services.auth_service import is_teacher_or_admin
from app.services.kpi_service import build_kpi_dashboard

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview")
def overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return core dashboard counters."""
    total_resources = db.query(func.count(Resource.id)).scalar() or 0
    low_inventory = (
        db.query(func.count(Resource.id))
        .filter(Resource.available_count <= Resource.min_threshold)
        .scalar()
        or 0
    )
    total_alerts = db.query(func.count(Alert.id)).scalar() or 0
    total_tx = db.query(func.count(Transaction.id)).scalar() or 0

    return {
        "total_resources": total_resources,
        "low_inventory_resources": low_inventory,
        "total_alerts": total_alerts,
        "total_transactions": total_tx,
    }


@router.get("/top-occupied-devices")
def top_occupied_devices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return device occupancy ranking."""
    devices = db.query(Resource).filter(Resource.category == "device", Resource.total_count > 0).all()
    ranked = []
    for resource in devices:
        occupancy = 1 - (resource.available_count / resource.total_count)
        ranked.append(
            {
                "resource_id": resource.id,
                "name": resource.name,
                "available_count": resource.available_count,
                "total_count": resource.total_count,
                "occupancy_rate": round(occupancy, 4),
            }
        )
    ranked.sort(key=lambda item: item["occupancy_rate"], reverse=True)
    return {"items": ranked[:10]}


@router.get("/waste-risk")
def waste_risk(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return suspicious high-volume consumption statistics."""
    items = (
        db.query(
            Transaction.resource_id,
            func.count(Transaction.id).label("times"),
            func.sum(Transaction.quantity).label("total_quantity"),
        )
        .filter(Transaction.action == "consume", Transaction.quantity >= 10)
        .group_by(Transaction.resource_id)
        .all()
    )
    return {
        "items": [
            {
                "resource_id": resource_id,
                "risk_times": times,
                "risk_total_quantity": total_quantity or 0,
            }
            for resource_id, times, total_quantity in items
        ]
    }


@router.get("/kpi-dashboard", response_model=KPIDashboardResponse)
def kpi_dashboard(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return KPI board with baseline/current/improvement and metric dictionary."""
    if not is_teacher_or_admin(current_user):
        raise HTTPException(status_code=403, detail="Only teachers or admins can view KPI dashboard")
    return KPIDashboardResponse(**build_kpi_dashboard(db, days=days))
