"""Rule-based business tools for the lab assistant."""

from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.models import User
from app.services.agent_tool_service import run_business_query


def ask_agent(db: Session, question: str, current_user: Optional[User] = None) -> Dict[str, object]:
    """Public deterministic agent entry point."""
    result = run_business_query(db, question, current_user)
    return {
        "intent": result["intent"],
        "answer": result["answer"],
        "analysis_steps": result.get("analysis_steps", []),
    }
