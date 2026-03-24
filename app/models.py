"""数据库 ORM 模型定义。"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Resource(Base):
    """共享资源模型：既可表示设备，也可表示物料。"""

    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, index=True)
    category = Column(String(50), nullable=False, index=True)  # device/material
    subtype = Column(String(80), nullable=False)  # 3D打印机/开发板等
    location = Column(String(120), default="创新实践基地")
    total_count = Column(Integer, default=1)
    available_count = Column(Integer, default=1)
    unit_cost = Column(Float, default=0.0)
    min_threshold = Column(Integer, default=1)
    status = Column(String(30), default="active")  # active/maintenance/disabled
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transactions = relationship("Transaction", back_populates="resource")


class Transaction(Base):
    """借还/领用流水，用于追踪占用不均、丢失和浪费风险。"""

    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    resource_id = Column(ForeignKey("resources.id"), nullable=False)
    user_name = Column(String(80), nullable=False, index=True)
    action = Column(String(30), nullable=False)  # borrow/return/consume/replenish/lost
    quantity = Column(Integer, default=1)
    note = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    resource = relationship("Resource", back_populates="transactions")


class Alert(Base):
    """系统预警：库存不足、设备占用不均、疑似浪费等。"""

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    level = Column(String(20), default="info")  # info/warn/error
    type = Column(String(40), nullable=False, index=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ChatMessage(Base):
    """多轮对话消息模型，用于保存每个会话上下文。"""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # system/user/assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
