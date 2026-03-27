"""SQLAlchemy ORM models."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Resource(Base):
    """Shared devices and consumables."""

    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, index=True)
    category = Column(String(50), nullable=False, index=True)  # device/material
    subtype = Column(String(80), nullable=False)
    location = Column(String(120), default="Innovation Lab")
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
    """System user."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    real_name = Column(String(100), nullable=False)
    student_id = Column(String(20), nullable=False, index=True)
    email = Column(String(100))
    role = Column(String(20), default="student")  # student/teacher/admin
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transactions = relationship("Transaction", back_populates="user")
    approval_tasks_requested = relationship(
        "ApprovalTask",
        foreign_keys="ApprovalTask.requester_id",
        back_populates="requester",
    )
    approval_tasks_approved = relationship(
        "ApprovalTask",
        foreign_keys="ApprovalTask.approver_id",
        back_populates="approver",
    )


class Transaction(Base):
    """Lifecycle record for applications, inventory changes, and returns."""

    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    resource_id = Column(ForeignKey("resources.id"), nullable=False, index=True)
    user_id = Column(ForeignKey("users.id"), nullable=False, index=True)
    action = Column(String(30), nullable=False)  # borrow/consume/replenish/lost/adjust
    quantity = Column(Integer, default=1)
    note = Column(Text, default="")

    borrow_time = Column(DateTime, nullable=True)
    return_time = Column(DateTime, nullable=True)
    expected_return_time = Column(DateTime, nullable=True)
    duration_minutes = Column(Integer, nullable=True)

    purpose = Column(String(200), default="")
    condition_return = Column(String(30), default="good")

    is_approved = Column(Boolean, default=False)
    status = Column(String(20), default="pending", nullable=False, index=True)
    inventory_applied = Column(Boolean, default=False, nullable=False)
    inventory_before_total = Column(Integer, nullable=True)
    inventory_after_total = Column(Integer, nullable=True)
    inventory_before_available = Column(Integer, nullable=True)
    inventory_after_available = Column(Integer, nullable=True)
    return_inventory_before_available = Column(Integer, nullable=True)
    return_inventory_after_available = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    resource = relationship("Resource", back_populates="transactions")
    user = relationship("User", back_populates="transactions")
    approval_task = relationship(
        "ApprovalTask",
        back_populates="transaction",
        uselist=False,
        foreign_keys="ApprovalTask.transaction_id",
    )


class Alert(Base):
    """System alert."""

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    level = Column(String(20), default="info")  # info/warn/error
    type = Column(String(40), nullable=False, index=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ApprovalTask(Base):
    """Approval record for a pending application."""

    __tablename__ = "approval_tasks"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(ForeignKey("transactions.id"), nullable=False, index=True)
    requester_id = Column(ForeignKey("users.id"), nullable=False, index=True)
    approver_id = Column(ForeignKey("users.id"), nullable=True)
    status = Column(String(20), default="pending")  # pending/approved/rejected
    reason = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    approved_at = Column(DateTime, nullable=True)

    transaction = relationship("Transaction", back_populates="approval_task", foreign_keys=[transaction_id])
    requester = relationship("User", foreign_keys=[requester_id], back_populates="approval_tasks_requested")
    approver = relationship("User", foreign_keys=[approver_id], back_populates="approval_tasks_approved")


class ChatMessage(Base):
    """Stored chat history for the agent assistant."""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # system/user/assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
