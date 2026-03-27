"""Pydantic request and response schemas."""

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ORMBaseModel(BaseModel):
    """Base schema with ORM parsing enabled."""

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    """Public registration payload."""

    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")
    real_name: str = Field(..., description="Real name")
    student_id: str = Field(..., description="Student or employee id")
    email: Optional[str] = None


class UserLogin(BaseModel):
    """Login payload."""

    username: str
    password: str


class UserOut(ORMBaseModel):
    """Serialized user."""

    id: int
    username: str
    real_name: str
    student_id: str
    email: Optional[str]
    role: str
    is_active: bool
    created_at: datetime


class LoginOut(BaseModel):
    """Login response."""

    token: str
    user: UserOut


class ResourceBase(BaseModel):
    """Common resource fields."""

    name: str
    category: Literal["device", "material"]
    subtype: str
    location: str = "Innovation Lab"
    total_count: int = 1
    available_count: int = 1
    unit_cost: float = 0.0
    min_threshold: int = 1
    status: str = "active"
    description: str = ""


class ResourceCreate(ResourceBase):
    """Create resource payload."""


class ResourceUpdate(BaseModel):
    """Update resource payload."""

    name: Optional[str] = None
    category: Optional[Literal["device", "material"]] = None
    subtype: Optional[str] = None
    location: Optional[str] = None
    total_count: Optional[int] = None
    available_count: Optional[int] = None
    unit_cost: Optional[float] = None
    min_threshold: Optional[int] = None
    status: Optional[str] = None
    description: Optional[str] = None


class ResourceOut(ORMBaseModel):
    """Serialized resource."""

    id: int
    name: str
    category: str
    subtype: str
    location: str
    total_count: int
    available_count: int
    unit_cost: float
    min_threshold: int
    status: str
    description: str
    created_at: datetime
    updated_at: datetime


class TransactionCreate(BaseModel):
    """Create transaction payload."""

    resource_id: int
    action: Literal["borrow", "consume", "replenish", "lost"]
    quantity: int = Field(default=1, ge=1)
    note: str = ""
    borrow_time: Optional[datetime] = None
    expected_return_time: Optional[datetime] = None
    purpose: str = ""


class ReturnRequest(BaseModel):
    """Return a borrowed device."""

    condition_return: Literal["good", "damaged", "partial_lost"] = "good"
    note: str = ""


class InventoryAdjustmentRequest(BaseModel):
    """Admin direct inventory adjustment payload."""

    target_total_count: int = Field(..., ge=0)
    target_available_count: int = Field(..., ge=0)
    reason: str = Field(..., min_length=1)


class TransactionOut(BaseModel):
    """Front-end DTO for transaction records."""

    id: int
    resource_id: int
    resource_name: str
    resource_category: str
    user_id: int
    requester_name: str
    requester_role: str
    action: str
    quantity: int
    note: str
    purpose: str
    status: str
    approval_status: str
    approval_id: Optional[int]
    borrow_time: Optional[datetime]
    expected_return_time: Optional[datetime]
    return_time: Optional[datetime]
    duration_minutes: Optional[int]
    condition_return: str
    can_return: bool
    inventory_applied: bool
    inventory_before_total: Optional[int]
    inventory_after_total: Optional[int]
    inventory_before_available: Optional[int]
    inventory_after_available: Optional[int]
    return_inventory_before_available: Optional[int]
    return_inventory_after_available: Optional[int]
    created_at: datetime


class ApprovalTaskOut(BaseModel):
    """Front-end DTO for approval cards."""

    id: int
    transaction_id: int
    requester_id: int
    requester_name: str
    requester_role: str
    approver_id: Optional[int]
    approver_name: Optional[str]
    resource_id: int
    resource_name: str
    resource_category: str
    action: str
    quantity: int
    note: str
    purpose: str
    status: str
    reason: str
    created_at: datetime
    approved_at: Optional[datetime]
    can_approve: bool
    suggestion: str


class ApprovalTaskApprove(BaseModel):
    """Approve or reject a task."""

    approved: bool
    reason: str = ""


class MessageOut(BaseModel):
    """Simple status message."""

    message: str


class AlertOut(ORMBaseModel):
    """Alert DTO."""

    id: int
    level: str
    type: str
    message: str
    created_at: datetime


class AgentAskIn(BaseModel):
    """Single-turn agent request."""

    question: str


class AgentAskOut(BaseModel):
    """Single-turn agent response."""

    intent: str
    answer: str


class AgentChatIn(BaseModel):
    """Chat request."""

    message: str
    session_id: Optional[str] = None


class AgentChatOut(BaseModel):
    """Chat response."""

    session_id: str
    reply: str
    used_model: bool


class ChatMessageOut(ORMBaseModel):
    """Stored chat message."""

    role: str
    content: str
    created_at: datetime


class EnhancedAgentRequest(BaseModel):
    """Enhanced agent payload."""

    question: str
    session_id: Optional[str] = "default"


class EnhancedAgentResponse(BaseModel):
    """Enhanced agent response."""

    session_id: str
    answer: str
    success: bool
    real_time_data: dict


class SchedulerRequest(BaseModel):
    """Scheduling request."""

    resource_id: int
    duration_minutes: int
    preferred_start: Optional[datetime] = None


class TimeSlot(BaseModel):
    """Recommended time slot."""

    start: datetime
    end: datetime
    day: str
    hour: int
    score: float
    conflicts: List[Dict] = Field(default_factory=list)


class SchedulerResponse(BaseModel):
    """Scheduling response."""

    resource_id: int
    duration_minutes: int
    optimal_slots: List[TimeSlot]
    generated_at: datetime


class DemandPrediction(BaseModel):
    """Demand forecast item."""

    date: str
    predicted_demand: float
    confidence: float
    recommendation: str


class DemandPredictionResponse(BaseModel):
    """Demand forecast response."""

    resource_id: int
    days_ahead: int
    predictions: List[DemandPrediction]
    generated_at: datetime


class OptimizationRecommendation(BaseModel):
    """Optimization recommendation."""

    resource_id: int
    resource_name: str
    utilization: float
    recommendation: str
    priority: str


class OptimizationResponse(BaseModel):
    """Resource optimization response."""

    total_devices: int
    recommendations: List[OptimizationRecommendation]
    generated_at: datetime


class PeriodInfo(BaseModel):
    """Analytics period metadata."""

    start_date: str
    end_date: str
    days: int


class SummaryStats(BaseModel):
    """Analytics summary."""

    total_transactions: int
    active_users: int
    average_device_utilization: float
    material_consumption: int
    daily_avg_transactions: float


class ResourceUsageAnalysis(BaseModel):
    """Resource analytics."""

    popular_resources: List[Dict]
    high_utilization_devices: List[Dict]
    analysis_period: str


class UserBehaviorAnalysis(BaseModel):
    """User analytics."""

    top_users: List[Dict]
    user_patterns: List[Dict]


class CostAnalysis(BaseModel):
    """Cost analytics."""

    total_cost: float
    daily_avg_cost: float
    cost_breakdown: List[Dict]
    high_cost_items: List[Dict]


class TrendAnalysis(BaseModel):
    """Trend analytics."""

    daily_usage: List[Dict]
    resource_category_trends: List[Dict]


class AnalyticsRecommendation(BaseModel):
    """Analytics recommendation."""

    type: str
    resource_id: int
    resource_name: str
    message: str
    priority: str


class AnalyticsResponse(BaseModel):
    """Composite analytics response."""

    period: PeriodInfo
    summary: SummaryStats
    resource_analysis: ResourceUsageAnalysis
    user_behavior: UserBehaviorAnalysis
    cost_analysis: CostAnalysis
    trends: TrendAnalysis
    recommendations: List[AnalyticsRecommendation]
