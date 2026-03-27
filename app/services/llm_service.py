"""LLM-backed chat service with deterministic business-tool fallback."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models import Alert, ChatMessage, Resource, Transaction
from app.services.agent_service import ask_agent, run_business_tool


def _build_data_context(db: Session) -> str:
    """Build a small business snapshot for the language model."""
    low_items = (
        db.query(Resource)
        .filter(Resource.available_count <= Resource.min_threshold)
        .order_by(Resource.available_count.asc())
        .limit(10)
        .all()
    )
    latest_alerts = db.query(Alert).order_by(Alert.created_at.desc()).limit(8).all()
    latest_tx = (
        db.query(Transaction)
        .options(joinedload(Transaction.user), joinedload(Transaction.resource))
        .order_by(Transaction.created_at.desc())
        .limit(8)
        .all()
    )

    lines: List[str] = ["[Low inventory]"]
    if low_items:
        for resource in low_items:
            lines.append(
                f"- {resource.name}: available {resource.available_count}, threshold {resource.min_threshold}"
            )
    else:
        lines.append("- none")

    lines.append("[Recent alerts]")
    if latest_alerts:
        for alert in latest_alerts:
            lines.append(f"- [{alert.level}] {alert.type}: {alert.message}")
    else:
        lines.append("- none")

    lines.append("[Recent transactions]")
    if latest_tx:
        for tx in latest_tx:
            user_name = tx.user.real_name if tx.user else f"User#{tx.user_id}"
            resource_name = tx.resource.name if tx.resource else f"Resource#{tx.resource_id}"
            lines.append(
                f"- {user_name} {tx.action} {resource_name} x{tx.quantity} status={tx.status}"
            )
    else:
        lines.append("- none")

    return "\n".join(lines)


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
    db.commit()


def list_sessions(db: Session, limit: int = 20) -> List[str]:
    """Return recent chat session ids."""
    rows = (
        db.query(ChatMessage.session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit * 4)
        .all()
    )
    session_ids: List[str] = []
    for row in rows:
        session_id = row[0]
        if session_id not in session_ids:
            session_ids.append(session_id)
        if len(session_ids) >= limit:
            break
    return session_ids


def get_session_messages(db: Session, session_id: str, limit: int = 50) -> List[ChatMessage]:
    """Return stored session messages."""
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
        .all()
    )


def clear_session_messages(db: Session, session_id: str) -> int:
    """Delete one chat session history."""
    deleted = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
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


def chat_with_agent(db: Session, user_message: str, session_id: Optional[str] = None) -> dict:
    """Chat entry point that uses business tools first, then optionally an LLM."""
    sid = session_id or uuid.uuid4().hex
    _save_message(db, sid, "user", user_message)

    tool_result = run_business_tool(db, user_message)
    deterministic_answer = tool_result["answer"]

    if settings.llm_enabled:
        try:
            system_prompt = (
                "You are the lab resource management assistant. "
                "Always ground your answer in the provided tool result and business context. "
                "Do not invent inventory numbers or approval decisions. Respond in Chinese."
            )
            context_text = _build_data_context(db)
            history = _load_history(db, sid)
            messages = [
                {
                    "role": "system",
                    "content": (
                        f"{system_prompt}\n\nBusiness snapshot:\n{context_text}\n\n"
                        f"Selected tool: {tool_result['intent']}\nTool output:\n{deterministic_answer}"
                    ),
                },
                *history,
                {
                    "role": "user",
                    "content": "Please answer the latest user request using the tool output above. "
                    "Include a short recommendation when appropriate.",
                },
            ]
            reply = _call_openai_compatible(messages)
            _save_message(db, sid, "assistant", reply)
            return {"session_id": sid, "reply": reply, "used_model": True}
        except Exception as exc:
            reply = f"{deterministic_answer}\n\n(LLM unavailable, using deterministic business tools only: {exc})"
            _save_message(db, sid, "assistant", reply)
            return {"session_id": sid, "reply": reply, "used_model": False}

    _save_message(db, sid, "assistant", deterministic_answer)
    return {"session_id": sid, "reply": deterministic_answer, "used_model": False}
