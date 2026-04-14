"""Final-stage readiness diagnostics for competition demos."""

from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import FollowUpTask, Resource, Transaction, User
from app.services.llm_service import check_llm_connectivity


def _safe_db_ping(db: Session) -> bool:
    try:
        db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def build_readiness_report(db: Session, *, probe_llm: bool = False) -> Dict[str, Any]:
    """Return a competition-facing readiness report with actionable checks."""
    db_ok = _safe_db_ping(db)
    resource_count = db.query(Resource.id).count()
    user_count = db.query(User.id).count()
    transaction_count = db.query(Transaction.id).count()
    open_follow_up_count = db.query(FollowUpTask.id).filter(FollowUpTask.status.in_(["open", "in_progress"])).count()

    llm_configured = bool(settings.llm_base_url and settings.llm_api_key and settings.llm_model)
    llm_status: Dict[str, Any] = {
        "ok": llm_configured if settings.llm_enabled else True,
        "reason": "config_present" if llm_configured else "config_missing",
        "message": "LLM config detected" if llm_configured else "LLM config missing",
    }
    if settings.llm_enabled and llm_configured and probe_llm:
        llm_status = check_llm_connectivity()

    insecure_jwt_secret = settings.jwt_secret.strip() == "change-me-in-env"
    seeded = resource_count >= 2 and user_count >= 3

    score = 100
    if not db_ok:
        score -= 40
    if insecure_jwt_secret:
        score -= 20
    if not seeded:
        score -= 15
    if settings.llm_enabled and not llm_configured:
        score -= 15
    if settings.llm_enabled and llm_configured and probe_llm and not llm_status.get("ok", False):
        score -= 10

    score = max(0, min(score, 100))
    level = "ready" if score >= 85 else "attention" if score >= 65 else "risk"

    checks = [
        {"name": "database", "ok": db_ok, "detail": "Database connectivity"},
        {"name": "seed_data", "ok": seeded, "detail": "Users/resources initialized for demo"},
        {"name": "jwt_secret", "ok": not insecure_jwt_secret, "detail": "JWT secret is not default"},
        {
            "name": "llm_config",
            "ok": (not settings.llm_enabled) or llm_configured,
            "detail": "LLM configuration completeness",
        },
    ]
    if settings.llm_enabled and probe_llm:
        checks.append(
            {
                "name": "llm_connectivity",
                "ok": bool(llm_status.get("ok")),
                "detail": llm_status.get("message", "LLM connectivity probe"),
            }
        )

    recommendations = [
        "设置强随机 JWT_SECRET 后再进行公开演示" if insecure_jwt_secret else "",
        "补充基础演示数据（至少 3 个账号、2 类资源）" if not seeded else "",
        "为现场演示配置可用的大模型 Base URL / API Key / Model" if settings.llm_enabled and not llm_configured else "",
    ]

    return {
        "service": settings.app_name,
        "environment": settings.app_env,
        "readiness_score": score,
        "readiness_level": level,
        "checks": checks,
        "stats": {
            "users": user_count,
            "resources": resource_count,
            "transactions": transaction_count,
            "open_follow_up_tasks": open_follow_up_count,
        },
        "llm": llm_status,
        "recommendations": [item for item in recommendations if item],
    }
