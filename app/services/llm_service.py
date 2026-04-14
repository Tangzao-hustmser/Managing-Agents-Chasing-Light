"""LLM-backed chat service with executable business-tool support."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass
class LLMRuntimeConfig:
    """Runtime LLM connection config resolved from request overrides and env."""

    base_url: str
    api_key: str
    model: str
    timeout: int


def _clean_optional_str(value: Optional[str]) -> str:
    return (value or "").strip()


def _resolve_runtime_config(llm_options: Optional[Dict[str, Any]] = None) -> Optional[LLMRuntimeConfig]:
    """Resolve per-request LLM config; request-level overrides take precedence."""
    def _safe_timeout(raw_value: Any) -> int:
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return int(settings.llm_timeout)

    if llm_options:
        if llm_options.get("enabled") is False:
            return None
        base_url = _clean_optional_str(llm_options.get("base_url")) or _clean_optional_str(settings.llm_base_url)
        api_key = _clean_optional_str(llm_options.get("api_key")) or _clean_optional_str(settings.llm_api_key)
        model = _clean_optional_str(llm_options.get("model")) or _clean_optional_str(settings.llm_model)
        timeout = _safe_timeout(llm_options.get("timeout") or settings.llm_timeout)
    else:
        if not settings.llm_enabled:
            return None
        base_url = _clean_optional_str(settings.llm_base_url)
        api_key = _clean_optional_str(settings.llm_api_key)
        model = _clean_optional_str(settings.llm_model)
        timeout = _safe_timeout(settings.llm_timeout)

    if not base_url or not api_key or not model:
        return None

    return LLMRuntimeConfig(
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        model=model,
        timeout=max(5, min(timeout, 120)),
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


def _call_openai_compatible(messages: List[Dict[str, str]], runtime_config: LLMRuntimeConfig) -> str:
    """Call an OpenAI-compatible /chat/completions endpoint."""
    payload: Dict[str, Any] = {
        "model": runtime_config.model,
        "messages": messages,
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {runtime_config.api_key}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(connect=5.0, read=float(runtime_config.timeout), write=10.0, pool=5.0)
    with httpx.Client(timeout=timeout) as client:
        response = client.post(f"{runtime_config.base_url}/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()


def get_llm_response(messages: List[Dict[str, str]]) -> str:
    """Compatibility wrapper for other modules."""
    runtime_config = _resolve_runtime_config()
    if not runtime_config:
        raise ValueError("LLM configuration is incomplete")
    return _call_openai_compatible(messages, runtime_config)


def check_llm_connectivity() -> dict:
    """Probe the configured model endpoint."""
    runtime_config = _resolve_runtime_config()
    if not runtime_config:
        return {
            "ok": False,
            "reason": "config_incomplete",
            "message": "LLM_BASE_URL / LLM_API_KEY / LLM_MODEL is not fully configured",
        }

    try:
        _call_openai_compatible([{"role": "user", "content": "ping"}], runtime_config)
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
    query_result: Dict[str, Any],
    current_user: User,
    llm_options: Optional[Dict[str, Any]] = None,
) -> tuple[str, bool]:
    deterministic_answer = query_result["answer"]
    runtime_config = _resolve_runtime_config(llm_options)
    if not runtime_config:
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
                    "Do not invent inventory numbers or approval decisions. "
                    "The first sentence must directly answer the user's question. "
                    "If the user asks about scheduling/availability, include one recommended start time and a brief reason. "
                    "Respond in Chinese."
                ),
            },
            {
                "role": "system",
                "content": f"Real-time context: {context_text}",
            },
            {
                "role": "system",
                "content": (
                    f"Deterministic tool intent: {query_result['intent']}. "
                    f"Deterministic tool answer: {deterministic_answer}. "
                    f"Analysis steps: {query_result.get('analysis_steps', [])}"
                ),
            },
            *history[-8:],
            {
                "role": "user",
                "content": f"请基于上面的事实，优化表达但不要改变结论；语气自然、可执行。当前用户：{current_user.real_name}。",
            },
        ]
        return _call_openai_compatible(messages, runtime_config), True
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
    llm_options: Optional[Dict[str, Any]] = None,
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
            "analysis_steps": [
                "感知输入：识别到确认指令。",
                "推理规划：校验待执行动作与确认令牌。",
                "执行输出：执行已提议动作并返回结果摘要。",
            ],
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
            "analysis_steps": [
                "感知输入：识别到取消指令。",
                "推理规划：清理会话中的待执行动作。",
                "执行输出：返回取消确认。",
            ],
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
            "analysis_steps": [
                "感知输入：识别到可执行业务动作请求。",
                "推理规划：生成待执行动作与参数草案，等待用户确认。",
                "执行输出：返回确认提示和动作令牌。",
            ],
            "confirmation_required": True,
            "pending_action": pending_action,
            "executed_tools": [],
        }

    query_result = run_business_query(db, user_message, current_user)
    reply, used_model = _maybe_refine_with_llm(db, sid, query_result, current_user, llm_options)
    _save_message(db, sid, "assistant", reply)
    return {
        "session_id": sid,
        "reply": reply,
        "used_model": used_model,
        "analysis_steps": query_result.get("analysis_steps", []),
        "confirmation_required": False,
        "pending_action": None,
        "executed_tools": [],
    }
