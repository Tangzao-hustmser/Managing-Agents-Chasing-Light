"""智能体会话管理路由。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import ChatMessageOut
from app.services.llm_service import clear_session_messages, get_session_messages, list_sessions

router = APIRouter(prefix="/agent", tags=["智能体会话"])


@router.get("/sessions")
def get_sessions(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)):
    """获取最近会话列表。"""
    return {"sessions": list_sessions(db, limit)}


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
def get_messages(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """获取指定会话消息。"""
    return get_session_messages(db, session_id, limit)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_db)):
    """清空指定会话消息。"""
    deleted = clear_session_messages(db, session_id)
    return {"session_id": session_id, "deleted_count": deleted}
