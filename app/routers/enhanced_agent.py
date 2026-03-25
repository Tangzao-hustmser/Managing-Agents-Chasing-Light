"""增强版智能体路由：支持真正的AI对话能力。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.routers.auth import get_current_user
from app.schemas import EnhancedAgentRequest, EnhancedAgentResponse
from app.services.enhanced_agent_service import enhanced_ask_agent

router = APIRouter(prefix="/enhanced-agent", tags=["增强版智能体"])


@router.post("/ask", response_model=EnhancedAgentResponse)
def enhanced_ask_agent_endpoint(
    payload: EnhancedAgentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    增强版智能问答：集成大语言模型实现真正的AI对话能力。
    
    支持多轮对话、上下文记忆、深度分析等功能。
    """
    try:
        result = enhanced_ask_agent(
            db=db,
            question=payload.question,
            session_id=payload.session_id or "default"
        )
        
        return EnhancedAgentResponse(
            session_id=result["session_id"],
            answer=result["answer"],
            success=result["success"],
            real_time_data=result["real_time_data"]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"智能体服务异常: {str(e)}")


@router.get("/health")
def enhanced_agent_health_check(db: Session = Depends(get_db)):
    """增强版智能体健康检查。"""
    from app.services.llm_service import check_llm_connectivity
    
    # 检查LLM连接状态
    llm_status = check_llm_connectivity()
    
    # 检查数据库连接
    try:
        db.execute("SELECT 1")
        db_status = "healthy"
    except Exception:
        db_status = "unhealthy"
    
    return {
        "service": "enhanced_agent",
        "status": "running",
        "llm": llm_status,
        "database": db_status
    }