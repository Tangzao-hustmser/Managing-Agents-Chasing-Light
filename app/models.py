"""数据库 ORM 模型定义。"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
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


class User(Base):
    """用户模型：支持多角色（学生、管理员、教师）。"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)  # 明文存储（演示用）
    real_name = Column(String(100), nullable=False)
    student_id = Column(String(20), nullable=False, index=True)  # 学号/工号
    email = Column(String(100))
    role = Column(String(20), default="student")  # student/admin/teacher
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transactions = relationship("Transaction", back_populates="user")
    approval_tasks_requested = relationship("ApprovalTask", foreign_keys="ApprovalTask.requester_id", back_populates="requester")
    approval_tasks_approved = relationship("ApprovalTask", foreign_keys="ApprovalTask.approver_id", back_populates="approver")


class Transaction(Base):
    """借还/领用流水，用于追踪占用不均、丢失和浪费风险。"""

    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    resource_id = Column(ForeignKey("resources.id"), nullable=False, index=True)
    user_id = Column(ForeignKey("users.id"), nullable=False, index=True)  # 操作用户
    action = Column(String(30), nullable=False)  # borrow/return/consume/replenish/lost
    quantity = Column(Integer, default=1)
    note = Column(Text, default="")
    
    # 时间维度
    borrow_time = Column(DateTime, nullable=True)  # 借用开始时间（设备类必填）
    return_time = Column(DateTime, nullable=True)  # 实际归还时间
    expected_return_time = Column(DateTime, nullable=True)  # 预期归还时间
    duration_minutes = Column(Integer, nullable=True)  # 借用时长（分钟）
    
    # 借还细节
    purpose = Column(String(200), default="")  # 使用目的
    condition_return = Column(String(30), default="完好")  # 归还状态：完好/损坏/部分丢失
    
    # 审批流程
    approval_id = Column(ForeignKey("approval_tasks.id"), nullable=True)
    is_approved = Column(Boolean, default=False)  # 是否已批准
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    resource = relationship("Resource", back_populates="transactions")
    user = relationship("User", back_populates="transactions")
    approval_task = relationship("ApprovalTask", foreign_keys=[approval_id], back_populates="transaction")


class Alert(Base):
    """系统预警：库存不足、设备占用不均、疑似浪费等。"""

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    level = Column(String(20), default="info")  # info/warn/error
    type = Column(String(40), nullable=False, index=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ApprovalTask(Base):
    """审批任务：高风险操作（大额消耗、丢失、补货）需要管理员审批。"""

    __tablename__ = "approval_tasks"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(ForeignKey("transactions.id"), nullable=False, index=True)
    requester_id = Column(ForeignKey("users.id"), nullable=False, index=True)  # 申请人
    approver_id = Column(ForeignKey("users.id"), nullable=True)  # 审批人
    status = Column(String(20), default="pending")  # pending/approved/rejected
    reason = Column(Text, default="")  # 审批理由或拒绝原因
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    approved_at = Column(DateTime, nullable=True)

    transaction = relationship("Transaction", foreign_keys=[transaction_id], back_populates="approval_task")
    requester = relationship("User", foreign_keys=[requester_id], back_populates="approval_tasks_requested")
    approver = relationship("User", foreign_keys=[approver_id], back_populates="approval_tasks_approved")


class ChatMessage(Base):
    """多轮对话消息模型，用于保存每个会话上下文。"""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # system/user/assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
