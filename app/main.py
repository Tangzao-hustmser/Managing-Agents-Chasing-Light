"""FastAPI application entry point."""

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.config import settings
from app.database import ensure_database_schema, get_db
from app.routers import agent, alerts, analytics, approvals, auth, files, resources, scheduler, transactions
from app.schemas import AgentAskIn, AgentAskOut, AgentChatIn, AgentChatOut
from app.services.agent_service import ask_agent
from app.services.llm_service import chat_with_agent, check_llm_connectivity

ensure_database_schema()

app = FastAPI(title=settings.app_name, version="1.1.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(resources.router)
app.include_router(transactions.router)
app.include_router(alerts.router)
app.include_router(approvals.router)
app.include_router(files.router)
app.include_router(analytics.router)
app.include_router(agent.router)
app.include_router(scheduler.router)


@app.get("/", tags=["system"])
def health_check():
    """Basic health check."""
    return {"name": settings.app_name, "status": "ok", "env": settings.app_env}


@app.get("/login", tags=["system"])
def login_page():
    """Return the login page."""
    return FileResponse("app/static/login.html")


@app.get("/dashboard", tags=["system"])
def dashboard_page():
    """Return the legacy demo page."""
    return FileResponse("app/static/dashboard.html")


@app.get("/dashboard-main", tags=["system"])
def dashboard_main_page():
    """Return the authenticated dashboard."""
    return FileResponse("app/static/dashboard-main.html")


@app.post("/agent/ask", response_model=AgentAskOut, tags=["agent"])
def agent_ask(payload: AgentAskIn, db: Session = Depends(get_db)):
    """Single-turn deterministic agent endpoint."""
    return AgentAskOut(**ask_agent(db, payload.question))


@app.post("/agent/chat", response_model=AgentChatOut, tags=["agent"])
def agent_chat(payload: AgentChatIn, db: Session = Depends(get_db)):
    """Chat endpoint backed by business tools and optional LLM summarization."""
    return AgentChatOut(**chat_with_agent(db, payload.message, payload.session_id))


@app.get("/debug/llm-check", tags=["diagnostics"])
def debug_llm_check():
    """Probe the configured LLM endpoint."""
    return check_llm_connectivity()
