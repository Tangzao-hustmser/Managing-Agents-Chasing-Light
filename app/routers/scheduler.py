"""智能调度路由：提供最优时段推荐和资源优化建议。"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.routers.auth import get_current_user
from app.schemas import SchedulerRequest, SchedulerResponse, DemandPredictionResponse, OptimizationResponse
from app.services.smart_scheduler import get_optimal_time_slots, predict_resource_demand, optimize_resource_allocation

router = APIRouter(prefix="/scheduler", tags=["智能调度"])


@router.post("/optimal-slots", response_model=SchedulerResponse)
def get_optimal_slots(
    payload: SchedulerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取最优使用时段推荐。
    
    基于历史数据、使用模式和冲突检测，智能推荐最佳使用时段。
    """
    try:
        slots = get_optimal_time_slots(
            db=db,
            resource_id=payload.resource_id,
            duration_minutes=payload.duration_minutes,
            preferred_start=payload.preferred_start
        )
        
        return SchedulerResponse(
            resource_id=payload.resource_id,
            duration_minutes=payload.duration_minutes,
            optimal_slots=slots,
            generated_at=datetime.utcnow()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"调度算法异常: {str(e)}")


@router.get("/demand-prediction/{resource_id}", response_model=DemandPredictionResponse)
def get_demand_prediction(
    resource_id: int,
    days_ahead: Optional[int] = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    预测未来资源需求。
    
    基于历史使用模式预测未来需求，帮助资源规划。
    """
    try:
        predictions = predict_resource_demand(
            db=db,
            resource_id=resource_id,
            days_ahead=days_ahead
        )
        
        return DemandPredictionResponse(
            resource_id=resource_id,
            days_ahead=days_ahead,
            predictions=predictions,
            generated_at=datetime.utcnow()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"需求预测异常: {str(e)}")


@router.get("/optimize-allocation", response_model=OptimizationResponse)
def optimize_allocation(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    优化资源分配策略。
    
    分析所有设备资源的使用情况，提供优化建议。
    """
    try:
        if not current_user.role == "admin":
            raise HTTPException(status_code=403, detail="仅管理员可访问资源优化功能")
        
        optimization_result = optimize_resource_allocation(db=db)
        
        return OptimizationResponse(
            total_devices=optimization_result["total_devices"],
            recommendations=optimization_result["recommendations"],
            generated_at=optimization_result["generated_at"]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"资源优化异常: {str(e)}")


@router.get("/health")
def scheduler_health_check():
    """智能调度服务健康检查。"""
    return {
        "service": "smart_scheduler",
        "status": "running",
        "features": [
            "optimal_time_slots",
            "demand_prediction", 
            "resource_optimization"
        ]
    }