"""Agent chat and session routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.routers.auth import get_current_user
from app.schemas import AgentAskIn, AgentAskOut, AgentChatIn, AgentChatOut, ChatMessageOut
from app.services.agent_service import ask_agent
from app.services.llm_service import chat_with_agent, clear_session_messages, get_session_messages, list_sessions

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/ask", response_model=AgentAskOut)
def agent_ask(
    payload: AgentAskIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Single-turn deterministic agent endpoint."""
    return AgentAskOut(**ask_agent(db, payload.question))


@router.post("/chat", response_model=AgentChatOut)
def agent_chat(
    payload: AgentChatIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Owner-bound tool-agent chat endpoint."""
    try:
        return AgentChatOut(
            **chat_with_agent(
                db,
                current_user,
                payload.message,
                payload.session_id,
                confirm=payload.confirm,
                confirmation_token=payload.confirmation_token,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/sessions")
def get_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List sessions owned by the current user."""
    return {"sessions": list_sessions(db, current_user, limit)}


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
def get_messages(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get one session's messages for the current user."""
    try:
        return get_session_messages(db, current_user, session_id, limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete one owned session."""
    try:
        deleted = clear_session_messages(db, current_user, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"session_id": session_id, "deleted_count": deleted}
