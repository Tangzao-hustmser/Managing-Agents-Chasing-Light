"""大模型调用服务（OpenAI 兼容接口）。"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Alert, ChatMessage, Resource, Transaction
from app.services.agent_service import ask_agent


def _build_data_context(db: Session) -> str:
    """构建轻量业务上下文，让模型回答更贴近当前库存与预警状态。"""
    low_items = (
        db.query(Resource)
        .filter(Resource.available_count <= Resource.min_threshold)
        .order_by(Resource.available_count.asc())
        .limit(10)
        .all()
    )
    latest_alerts = db.query(Alert).order_by(Alert.created_at.desc()).limit(8).all()
    latest_tx = db.query(Transaction).order_by(Transaction.created_at.desc()).limit(8).all()

    lines: list[str] = []
    lines.append("【低库存资源】")
    if low_items:
        for r in low_items:
            lines.append(f"- {r.name}: 可用{r.available_count}, 阈值{r.min_threshold}")
    else:
        lines.append("- 无")

    lines.append("【最近预警】")
    if latest_alerts:
        for a in latest_alerts:
            lines.append(f"- [{a.level}] {a.type}: {a.message}")
    else:
        lines.append("- 无")

    lines.append("【最近流水】")
    if latest_tx:
        for t in latest_tx:
            lines.append(f"- {t.user_name} {t.action} 资源#{t.resource_id} 数量{t.quantity}")
    else:
        lines.append("- 无")

    return "\n".join(lines)


def _load_history(db: Session, session_id: str, limit: int = 12) -> list[dict[str, str]]:
    """读取历史消息，限制条数以控制 token 成本。"""
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
        .all()
    )
    return [{"role": row.role, "content": row.content} for row in rows]


def _save_message(db: Session, session_id: str, role: str, content: str) -> None:
    """持久化一条会话消息，便于多轮追问。"""
    db.add(ChatMessage(session_id=session_id, role=role, content=content))
    db.commit()


def list_sessions(db: Session, limit: int = 20) -> list[str]:
    """返回最近会话 ID 列表。"""
    rows = (
        db.query(ChatMessage.session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit * 4)
        .all()
    )
    session_ids: list[str] = []
    for row in rows:
        sid = row[0]
        if sid not in session_ids:
            session_ids.append(sid)
        if len(session_ids) >= limit:
            break
    return session_ids


def get_session_messages(db: Session, session_id: str, limit: int = 50) -> list[ChatMessage]:
    """读取指定会话消息，便于前端展示聊天记录。"""
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
        .all()
    )


def clear_session_messages(db: Session, session_id: str) -> int:
    """清理会话历史，保护隐私并减少存储。"""
    deleted = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    db.commit()
    return deleted


def _call_openai_compatible(messages: list[dict[str, str]]) -> str:
    """调用 OpenAI 兼容接口 `/chat/completions`。"""
    base_url = settings.llm_base_url.rstrip("/")
    if not base_url or not settings.llm_api_key or not settings.llm_model:
        raise ValueError("大模型配置不完整，请检查 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL")

    payload: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    # 将连接超时单独收紧，避免网关异常时长时间阻塞页面体验。
    timeout = httpx.Timeout(connect=5.0, read=float(settings.llm_timeout), write=10.0, pool=5.0)
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


def check_llm_connectivity() -> dict:
    """主动检查大模型连接状态，便于前端/答辩现场快速排障。"""
    base_url = settings.llm_base_url.rstrip("/")
    if not base_url or not settings.llm_api_key or not settings.llm_model:
        return {
            "ok": False,
            "reason": "config_incomplete",
            "message": "大模型配置不完整，请检查 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL",
        }

    probe_messages = [{"role": "user", "content": "ping"}]
    try:
        _call_openai_compatible(probe_messages)
        return {"ok": True, "reason": "success", "message": "大模型连接成功"}
    except httpx.ConnectError as exc:
        text = str(exc).lower()
        if "getaddrinfo failed" in text or "name or service not known" in text:
            return {
                "ok": False,
                "reason": "dns_error",
                "message": "网关域名无法解析，请检查 LLM_BASE_URL 是否正确，或切换可用 DNS/网络",
                "detail": str(exc),
            }
        return {
            "ok": False,
            "reason": "connect_error",
            "message": "无法连接模型网关，请检查网络或代理设置",
            "detail": str(exc),
        }
    except httpx.HTTPStatusError as exc:
        return {
            "ok": False,
            "reason": "http_error",
            "message": f"模型网关返回 HTTP {exc.response.status_code}，请检查 Key/模型名/账户权限",
            "detail": exc.response.text[:300],
        }
    except Exception as exc:
        return {"ok": False, "reason": "unknown_error", "message": "模型调用异常", "detail": str(exc)}


def chat_with_agent(db: Session, user_message: str, session_id: str | None = None) -> dict:
    """对话式智能体入口：优先调用大模型，失败时回退规则引擎。"""
    sid = session_id or uuid.uuid4().hex
    _save_message(db, sid, "user", user_message)

    if settings.llm_enabled:
        try:
            system_prompt = (
                "你是高校创新实践基地设备与物料管理智能体。"
                "你的目标是提高资源利用率、减少浪费、降低丢失。"
                "回答要基于给定业务上下文，给出可执行建议，语言使用中文。"
            )
            context_text = _build_data_context(db)
            history = _load_history(db, sid)
            messages = [{"role": "system", "content": system_prompt + "\n\n" + context_text}] + history
            reply = _call_openai_compatible(messages)
            _save_message(db, sid, "assistant", reply)
            return {"session_id": sid, "reply": reply, "used_model": True}
        except Exception as exc:
            # 当模型调用失败时，自动回退本地规则引擎，保证可用性。
            fallback = ask_agent(db, user_message)["answer"]
            text = str(exc)
            if "getaddrinfo failed" in text.lower():
                text = "模型网关域名无法解析，请检查 LLM_BASE_URL 是否正确或网络 DNS 设置"
            reply = f"（模型调用失败，已回退规则引擎：{text}）\n{fallback}"
            _save_message(db, sid, "assistant", reply)
            return {"session_id": sid, "reply": reply, "used_model": False}

    fallback = ask_agent(db, user_message)["answer"]
    _save_message(db, sid, "assistant", fallback)
    return {"session_id": sid, "reply": fallback, "used_model": False}
