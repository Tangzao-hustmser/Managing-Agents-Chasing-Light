"""FastAPI 启动入口。"""

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db
from app.routers import agent, alerts, analytics, approvals, auth, files, resources, transactions
from app.schemas import AgentAskIn, AgentAskOut, AgentChatIn, AgentChatOut
from app.services.agent_service import ask_agent
from app.services.llm_service import chat_with_agent, check_llm_connectivity

# 应用启动时自动建表，便于快速演示和比赛答辩。
Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name, version="1.0.0")

# 挂载静态目录，用于管理面板页面资源访问。
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# 注册业务路由模块。
app.include_router(auth.router)
app.include_router(resources.router)
app.include_router(transactions.router)
app.include_router(alerts.router)
app.include_router(approvals.router)
app.include_router(files.router)
app.include_router(analytics.router)
app.include_router(agent.router)


@app.get("/", tags=["系统"])
def health_check():
    """健康检查接口。"""
    return {"name": settings.app_name, "status": "ok", "env": settings.app_env}


@app.get("/dashboard", tags=["系统"])
def dashboard_page():
    """返回前端管理面板页面。"""
    return FileResponse("app/static/dashboard.html")


@app.post("/agent/ask", response_model=AgentAskOut, tags=["智能体"])
def agent_ask(payload: AgentAskIn, db: Session = Depends(get_db)):
    """智能体问答接口：将自然语言请求转为管理洞察。"""
    result = ask_agent(db, payload.question)
    return AgentAskOut(**result)


@app.post("/agent/chat", response_model=AgentChatOut, tags=["智能体"])
def agent_chat(payload: AgentChatIn, db: Session = Depends(get_db)):
    """对话式智能体接口：支持多轮会话和上下文记忆。"""
    result = chat_with_agent(db, payload.message, payload.session_id)
    return AgentChatOut(**result)


@app.get("/debug/llm-check", tags=["系统诊断"])
def debug_llm_check():
    """一键诊断大模型连通性（不返回明文 Key）。"""
    return check_llm_connectivity()
