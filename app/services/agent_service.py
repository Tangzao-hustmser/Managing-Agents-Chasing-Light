"""Rule-based business tools for the lab assistant."""

from typing import Dict

from sqlalchemy.orm import Session

from app.services.agent_tool_service import run_business_query


def ask_agent(db: Session, question: str) -> Dict[str, str]:
    """Public deterministic agent entry point."""
    result = run_business_query(db, question)
    return {"intent": result["intent"], "answer": result["answer"]}
