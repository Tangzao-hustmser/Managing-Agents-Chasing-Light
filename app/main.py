"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import ensure_database_schema
from app.routers import agent, alerts, analytics, approvals, auth, files, resources, scheduler, transactions
from app.routers import enhanced_agent, enhanced_analytics
from app.services.llm_service import check_llm_connectivity

ensure_database_schema()

app = FastAPI(title=settings.app_name, version="1.2.0")
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
app.include_router(enhanced_agent.router)
app.include_router(enhanced_analytics.router)


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


@app.get("/debug/llm-check", tags=["diagnostics"])
def debug_llm_check():
    """Probe the configured LLM endpoint."""
    return check_llm_connectivity()
