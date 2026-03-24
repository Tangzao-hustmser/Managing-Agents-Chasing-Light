"""数据看板路由：用于答辩展示核心管理指标。"""

from sqlalchemy import func
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Alert, Resource, Transaction

router = APIRouter(prefix="/analytics", tags=["数据看板"])


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    """输出总览指标：资源数、低库存数、预警数、今日流水等。"""
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
def top_occupied_devices(db: Session = Depends(get_db)):
    """返回设备占用率排行榜，便于识别占用不均问题。"""
    devices = db.query(Resource).filter(Resource.category == "device", Resource.total_count > 0).all()
    ranked = []
    for d in devices:
        occupancy = 1 - (d.available_count / d.total_count)
        ranked.append(
            {
                "resource_id": d.id,
                "name": d.name,
                "available_count": d.available_count,
                "total_count": d.total_count,
                "occupancy_rate": round(occupancy, 4),
            }
        )
    ranked.sort(key=lambda x: x["occupancy_rate"], reverse=True)
    return {"items": ranked[:10]}


@router.get("/waste-risk")
def waste_risk(db: Session = Depends(get_db)):
    """统计疑似浪费行为（consume 且数量较大）。"""
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
