"""FastAPI application entry point."""

from fastapi import Depends, FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.config import settings
from app.database import ensure_database_schema, get_db
from app.routers import agent, alerts, analytics, approvals, auth, files, resources, scheduler, transactions
from app.routers import audit_logs
from app.routers import enhanced_agent, enhanced_analytics
from app.routers import follow_up_tasks
from app.routers import notifications
from app.services.llm_service import check_llm_connectivity
from app.services.readiness_service import build_readiness_report

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
app.include_router(follow_up_tasks.router)
app.include_router(notifications.router)
app.include_router(audit_logs.router)


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


@app.get("/system/readiness", tags=["diagnostics"])
def system_readiness(
    probe_llm: bool = Query(default=False, description="Whether to perform live LLM connectivity probe"),
    db: Session = Depends(get_db),
):
    """Return a final-stage readiness report for demo and competition validation."""
    return build_readiness_report(db, probe_llm=probe_llm)
