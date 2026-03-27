"""LLM-backed chat service with executable business-tool support."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ChatMessage, ChatSession, User
from app.services.agent_tool_service import (
    _is_cancel_message,
    _is_confirmation_message,
    build_action_proposal,
    clear_pending_action,
    ensure_chat_session,
    execute_pending_action,
    get_real_time_data_context,
    list_user_sessions,
    run_business_query,
    store_pending_action,
)


def _load_history(db: Session, session_id: str, limit: int = 12) -> List[Dict[str, str]]:
    """Read recent chat history."""
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
        .all()
    )
    return [{"role": row.role, "content": row.content} for row in rows]


def _save_message(db: Session, session_id: str, role: str, content: str) -> None:
    """Persist a chat message."""
    db.add(ChatMessage(session_id=session_id, role=role, content=content))
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if session:
        session.updated_at = datetime.utcnow()
        db.add(session)
    db.commit()


def list_sessions(db: Session, current_user: User, limit: int = 20) -> List[str]:
    """Return recent chat session ids for one owner."""
    return list_user_sessions(db, current_user, limit)


def _get_owned_session(db: Session, current_user: User, session_id: str) -> ChatSession:
    session = db.query(ChatSession).filter(ChatSession.session_id == session_id).first()
    if not session or session.owner_user_id != current_user.id:
        raise ValueError("Session does not belong to the current user")
    return session


def get_session_messages(db: Session, current_user: User, session_id: str, limit: int = 50) -> List[ChatMessage]:
    """Return stored session messages for one owner."""
    _get_owned_session(db, current_user, session_id)
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
        .all()
    )


def clear_session_messages(db: Session, current_user: User, session_id: str) -> int:
    """Delete one owned chat session history."""
    _get_owned_session(db, current_user, session_id)
    deleted = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    db.query(ChatSession).filter(ChatSession.session_id == session_id).delete()
    db.commit()
    return deleted


def _call_openai_compatible(messages: List[Dict[str, str]]) -> str:
    """Call an OpenAI-compatible /chat/completions endpoint."""
    base_url = settings.llm_base_url.rstrip("/")
    if not base_url or not settings.llm_api_key or not settings.llm_model:
        raise ValueError("LLM configuration is incomplete")

    payload: Dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(connect=5.0, read=float(settings.llm_timeout), write=10.0, pool=5.0)
    with httpx.Client(timeout=timeout) as client:
        response = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()


def get_llm_response(messages: List[Dict[str, str]]) -> str:
    """Compatibility wrapper for other modules."""
    return _call_openai_compatible(messages)


def check_llm_connectivity() -> dict:
    """Probe the configured model endpoint."""
    base_url = settings.llm_base_url.rstrip("/")
    if not base_url or not settings.llm_api_key or not settings.llm_model:
        return {
            "ok": False,
            "reason": "config_incomplete",
            "message": "LLM_BASE_URL / LLM_API_KEY / LLM_MODEL is not fully configured",
        }

    try:
        _call_openai_compatible([{"role": "user", "content": "ping"}])
        return {"ok": True, "reason": "success", "message": "LLM connectivity is healthy"}
    except httpx.ConnectError as exc:
        return {
            "ok": False,
            "reason": "connect_error",
            "message": "Cannot connect to the configured LLM endpoint",
            "detail": str(exc),
        }
    except httpx.HTTPStatusError as exc:
        return {
            "ok": False,
            "reason": "http_error",
            "message": f"LLM endpoint returned HTTP {exc.response.status_code}",
            "detail": exc.response.text[:300],
        }
    except Exception as exc:
        return {
            "ok": False,
            "reason": "unknown_error",
            "message": "Unexpected LLM error",
            "detail": str(exc),
        }


def _maybe_refine_with_llm(
    db: Session,
    session_id: str,
    query_result: Dict[str, str],
    current_user: User,
) -> tuple[str, bool]:
    deterministic_answer = query_result["answer"]
    if not settings.llm_enabled:
        return deterministic_answer, False

    try:
        context_text = get_real_time_data_context(db)
        history = _load_history(db, session_id)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are the lab resource management assistant. "
                    "Always ground your answer in the provided business tool output. "
                    "Do not invent inventory numbers or approval decisions. Respond in Chinese."
                ),
            },
            {
                "role": "system",
                "content": f"Real-time context: {context_text}",
            },
            {
                "role": "system",
                "content": f"Deterministic tool answer: {deterministic_answer}",
            },
            *history[-8:],
            {
                "role": "user",
                "content": f"请基于上面的事实，优化表达但不要改变结论。当前用户：{current_user.real_name}。",
            },
        ]
        return _call_openai_compatible(messages), True
    except Exception:
        return deterministic_answer, False


def chat_with_agent(
    db: Session,
    current_user: User,
    user_message: str,
    session_id: Optional[str] = None,
    *,
    confirm: bool = False,
    confirmation_token: Optional[str] = None,
) -> dict:
    """Chat entry point that supports executable business tools."""
    session = ensure_chat_session(db, session_id, current_user)
    sid = session.session_id
    _save_message(db, sid, "user", user_message)

    should_confirm = confirm or _is_confirmation_message(user_message)
    if should_confirm and session.pending_tool_name:
        result = execute_pending_action(db, session, current_user, confirmation_token)
        reply = result["summary"]
        _save_message(db, sid, "assistant", reply)
        return {
            "session_id": sid,
            "reply": reply,
            "used_model": False,
            "confirmation_required": False,
            "pending_action": None,
            "executed_tools": [{"name": result["name"], "status": "executed", "summary": reply}],
        }

    if _is_cancel_message(user_message) and session.pending_tool_name:
        clear_pending_action(session)
        db.add(session)
        db.commit()
        reply = "已取消待执行动作。"
        _save_message(db, sid, "assistant", reply)
        return {
            "session_id": sid,
            "reply": reply,
            "used_model": False,
            "confirmation_required": False,
            "pending_action": None,
            "executed_tools": [],
        }

    proposal = build_action_proposal(db, current_user, user_message)
    if proposal:
        pending_action = store_pending_action(session, proposal)
        db.add(session)
        db.commit()
        reply = (
            f"我可以为你执行：{pending_action['title']}。\n"
            "请发送“确认”继续，或发送“取消”放弃。"
        )
        _save_message(db, sid, "assistant", reply)
        return {
            "session_id": sid,
            "reply": reply,
            "used_model": False,
            "confirmation_required": True,
            "pending_action": pending_action,
            "executed_tools": [],
        }

    query_result = run_business_query(db, user_message)
    reply, used_model = _maybe_refine_with_llm(db, sid, query_result, current_user)
    _save_message(db, sid, "assistant", reply)
    return {
        "session_id": sid,
        "reply": reply,
        "used_model": used_model,
        "confirmation_required": False,
        "pending_action": None,
        "executed_tools": [],
    }
