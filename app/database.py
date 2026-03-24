"""数据库初始化与会话管理。"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

# SQLite 需要关闭同线程检查，以支持 FastAPI 的多请求场景。
connect_args = {"check_same_thread": False} if "sqlite" in settings.database_url else {}

# 创建数据库引擎，负责管理数据库连接。
engine = create_engine(settings.database_url, connect_args=connect_args)

# 创建会话工厂，每次请求都从这里获取独立 Session。
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 所有 ORM 模型都继承这个基类。
Base = declarative_base()


def get_db():
    """FastAPI 依赖注入函数：按请求提供数据库会话并自动释放。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
