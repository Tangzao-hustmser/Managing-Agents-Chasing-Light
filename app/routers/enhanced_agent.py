"""Enhanced agent routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.routers.auth import get_current_user
from app.schemas import EnhancedAgentRequest, EnhancedAgentResponse
from app.services.enhanced_agent_service import enhanced_ask_agent

router = APIRouter(prefix="/enhanced-agent", tags=["enhanced-agent"])


@router.post("/ask", response_model=EnhancedAgentResponse)
@router.post("/chat", response_model=EnhancedAgentResponse)
def enhanced_ask_agent_endpoint(
    payload: EnhancedAgentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Enhanced chat endpoint with real-time context and executable tools."""
    try:
        result = enhanced_ask_agent(
            db=db,
            current_user=current_user,
            question=payload.question,
            session_id=payload.session_id,
            confirm=payload.confirm,
            confirmation_token=payload.confirmation_token,
            llm_options=payload.llm_options.model_dump(exclude_none=True) if payload.llm_options else None,
        )
        return EnhancedAgentResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Enhanced agent error: {exc}") from exc


@router.get("/health")
def enhanced_agent_health_check(db: Session = Depends(get_db)):
    """Health check for the enhanced agent."""
    from app.services.llm_service import check_llm_connectivity

    llm_status = check_llm_connectivity()
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception:
        db_status = "unhealthy"

    return {
        "service": "enhanced_agent",
        "status": "running",
        "llm": llm_status,
        "database": db_status,
    }
