"""增强版数据分析路由：提供深度洞察和预测功能。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.routers.auth import get_current_user
from app.schemas import AnalyticsResponse, DemandPredictionResponse
from app.services.advanced_analytics import get_comprehensive_analytics, predict_future_demand

router = APIRouter(prefix="/enhanced-analytics", tags=["增强版数据分析"])


@router.get("/comprehensive", response_model=AnalyticsResponse)
def get_comprehensive_analytics_endpoint(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取综合数据分析报告。
    
    提供资源使用、用户行为、成本分析、趋势识别等多维度深度分析。
    """
    try:
        if not current_user.role == "admin":
            raise HTTPException(status_code=403, detail="仅管理员可访问综合数据分析功能")
        
        analytics_data = get_comprehensive_analytics(db=db, days=days)
        
        return AnalyticsResponse(
            period=analytics_data["period"],
            summary=analytics_data["summary"],
            resource_analysis=analytics_data["resource_analysis"],
            user_behavior=analytics_data["user_behavior"],
            cost_analysis=analytics_data["cost_analysis"],
            trends=analytics_data["trends"],
            recommendations=analytics_data["recommendations"]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据分析异常: {str(e)}")


@router.get("/demand-prediction/{resource_id}", response_model=DemandPredictionResponse)
def get_demand_prediction_endpoint(
    resource_id: int,
    days_ahead: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    预测未来资源需求。
    
    基于历史使用模式预测未来需求，帮助资源规划和管理决策。
    """
    try:
        if not current_user.role == "admin":
            raise HTTPException(status_code=403, detail="仅管理员可访问需求预测功能")
        
        prediction_data = predict_future_demand(
            db=db,
            resource_id=resource_id,
            days_ahead=days_ahead
        )
        
        return DemandPredictionResponse(
            resource_id=prediction_data["resource_id"],
            predictions=prediction_data["predictions"],
            prediction_method=prediction_data["prediction_method"],
            generated_at=prediction_data["generated_at"]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"需求预测异常: {str(e)}")


@router.get("/health")
def enhanced_analytics_health_check():
    """增强版数据分析服务健康检查。"""
    return {
        "service": "enhanced_analytics",
        "status": "running",
        "features": [
            "comprehensive_analytics",
            "demand_prediction",
            "trend_analysis",
            "cost_analysis"
        ]
    }