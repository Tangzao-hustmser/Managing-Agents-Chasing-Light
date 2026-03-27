"""SQLAlchemy ORM models."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Resource(Base):
    """Shared resource category stock."""

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
    items = relationship("ResourceItem", back_populates="resource")
    follow_up_tasks = relationship("FollowUpTask", back_populates="resource")


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
    borrowed_items = relationship(
        "ResourceItem",
        foreign_keys="ResourceItem.current_borrower_id",
        back_populates="current_borrower",
    )
    maintenance_records_authored = relationship(
        "MaintenanceRecord",
        foreign_keys="MaintenanceRecord.recorded_by_user_id",
        back_populates="recorded_by",
    )
    follow_up_tasks_assigned = relationship(
        "FollowUpTask",
        foreign_keys="FollowUpTask.assigned_user_id",
        back_populates="assigned_user",
    )
    chat_sessions = relationship("ChatSession", back_populates="owner")


class ResourceItem(Base):
    """Tracked physical asset instance for device resources."""

    __tablename__ = "resource_items"

    id = Column(Integer, primary_key=True, index=True)
    resource_id = Column(ForeignKey("resources.id"), nullable=False, index=True)
    asset_number = Column(String(64), nullable=False, unique=True, index=True)
    serial_number = Column(String(120), default="")
    qr_code = Column(String(255), default="")
    status = Column(String(30), default="available", index=True)
    current_location = Column(String(120), default="Innovation Lab")
    current_borrower_id = Column(ForeignKey("users.id"), nullable=True, index=True)
    maintenance_notes = Column(Text, default="")
    last_maintenance_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    resource = relationship("Resource", back_populates="items")
    current_borrower = relationship(
        "User",
        foreign_keys=[current_borrower_id],
        back_populates="borrowed_items",
    )
    maintenance_records = relationship("MaintenanceRecord", back_populates="resource_item")
    follow_up_tasks = relationship("FollowUpTask", back_populates="resource_item")
    transaction_links = relationship("TransactionItem", back_populates="resource_item")


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
    project_name = Column(String(120), default="")
    estimated_quantity = Column(Integer, nullable=True)
    condition_return = Column(String(30), default="good")
    evidence_url = Column(String(500), default="")
    evidence_type = Column(String(50), default="")

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
    item_links = relationship("TransactionItem", back_populates="transaction")
    follow_up_tasks = relationship("FollowUpTask", back_populates="transaction")


class TransactionItem(Base):
    """Link between a transaction and tracked resource instances."""

    __tablename__ = "transaction_items"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(ForeignKey("transactions.id"), nullable=False, index=True)
    resource_item_id = Column(ForeignKey("resource_items.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    transaction = relationship("Transaction", back_populates="item_links")
    resource_item = relationship("ResourceItem", back_populates="transaction_links")


class MaintenanceRecord(Base):
    """Maintenance and quarantine history for one resource item."""

    __tablename__ = "maintenance_records"

    id = Column(Integer, primary_key=True, index=True)
    resource_item_id = Column(ForeignKey("resource_items.id"), nullable=False, index=True)
    recorded_by_user_id = Column(ForeignKey("users.id"), nullable=True, index=True)
    status = Column(String(30), default="maintenance")
    description = Column(Text, default="")
    evidence_url = Column(String(500), default="")
    evidence_type = Column(String(50), default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    resolved_at = Column(DateTime, nullable=True)

    resource_item = relationship("ResourceItem", back_populates="maintenance_records")
    recorded_by = relationship(
        "User",
        foreign_keys=[recorded_by_user_id],
        back_populates="maintenance_records_authored",
    )


class FollowUpTask(Base):
    """Operational task raised by loss, maintenance, or audit anomalies."""

    __tablename__ = "follow_up_tasks"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(ForeignKey("transactions.id"), nullable=True, index=True)
    resource_id = Column(ForeignKey("resources.id"), nullable=False, index=True)
    resource_item_id = Column(ForeignKey("resource_items.id"), nullable=True, index=True)
    assigned_user_id = Column(ForeignKey("users.id"), nullable=True, index=True)
    task_type = Column(String(50), nullable=False, index=True)
    status = Column(String(20), default="open", index=True)
    title = Column(String(160), nullable=False)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    due_at = Column(DateTime, nullable=True)

    transaction = relationship("Transaction", back_populates="follow_up_tasks")
    resource = relationship("Resource", back_populates="follow_up_tasks")
    resource_item = relationship("ResourceItem", back_populates="follow_up_tasks")
    assigned_user = relationship(
        "User",
        foreign_keys=[assigned_user_id],
        back_populates="follow_up_tasks_assigned",
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


class ChatSession(Base):
    """Owner-bound chat session for the tool agent."""

    __tablename__ = "chat_sessions"

    session_id = Column(String(64), primary_key=True, index=True)
    owner_user_id = Column(ForeignKey("users.id"), nullable=False, index=True)
    pending_tool_name = Column(String(80), nullable=True)
    pending_tool_payload = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    owner = relationship("User", back_populates="chat_sessions")


class ChatMessage(Base):
    """Stored chat history for the agent assistant."""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # system/user/assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
