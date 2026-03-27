"""Enhanced agent service wrapper."""

from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.models import User
from app.services.agent_tool_service import get_real_time_data_context
from app.services.llm_service import chat_with_agent


def enhanced_ask_agent(
    db: Session,
    current_user: User,
    question: str,
    session_id: Optional[str] = None,
    *,
    confirm: bool = False,
    confirmation_token: Optional[str] = None,
    llm_options: Optional[Dict] = None,
) -> Dict:
    """Return enhanced agent output with real-time context."""
    result = chat_with_agent(
        db,
        current_user,
        question,
        session_id=session_id,
        confirm=confirm,
        confirmation_token=confirmation_token,
        llm_options=llm_options,
    )
    return {
        "session_id": result["session_id"],
        "answer": result["reply"],
        "success": True,
        "real_time_data": get_real_time_data_context(db),
        "confirmation_required": result.get("confirmation_required", False),
        "pending_action": result.get("pending_action"),
        "executed_tools": result.get("executed_tools", []),
    }
