"""Pydantic request and response schemas."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

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
    total_count: int = Field(default=1, ge=0)
    available_count: int = Field(default=1, ge=0)
    unit_cost: float = Field(default=0.0, ge=0)
    min_threshold: int = Field(default=1, ge=0)
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
    total_count: Optional[int] = Field(default=None, ge=0)
    available_count: Optional[int] = Field(default=None, ge=0)
    unit_cost: Optional[float] = Field(default=None, ge=0)
    min_threshold: Optional[int] = Field(default=None, ge=0)
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
    item_count: int = 0
    available_item_count: int = 0
    created_at: datetime
    updated_at: datetime


class ResourceItemBase(BaseModel):
    """Common resource-item fields."""

    asset_number: str
    serial_number: str = ""
    qr_code: str = ""
    status: str = "available"
    current_location: str = "Innovation Lab"
    current_borrower_id: Optional[int] = None
    maintenance_notes: str = ""


class ResourceItemCreate(ResourceItemBase):
    """Create resource item payload."""


class ResourceItemUpdate(BaseModel):
    """Update resource item payload."""

    asset_number: Optional[str] = None
    serial_number: Optional[str] = None
    qr_code: Optional[str] = None
    status: Optional[str] = None
    current_location: Optional[str] = None
    current_borrower_id: Optional[int] = None
    maintenance_notes: Optional[str] = None


class ResourceItemOut(ORMBaseModel):
    """Tracked resource instance."""

    id: int
    resource_id: int
    asset_number: str
    serial_number: str
    qr_code: str
    status: str
    current_location: str
    current_borrower_id: Optional[int]
    maintenance_notes: str
    last_maintenance_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class MaintenanceRecordCreate(BaseModel):
    """Maintenance record payload."""

    status: str = "maintenance"
    description: str = Field(..., min_length=1)
    evidence_url: str = ""
    evidence_type: str = ""


class MaintenanceRecordOut(ORMBaseModel):
    """Maintenance record."""

    id: int
    resource_item_id: int
    recorded_by_user_id: Optional[int]
    status: str
    description: str
    evidence_url: str
    evidence_type: str
    created_at: datetime
    resolved_at: Optional[datetime]


class FollowUpTaskOut(ORMBaseModel):
    """Operational follow-up task."""

    id: int
    transaction_id: Optional[int]
    resource_id: int
    resource_item_id: Optional[int]
    assigned_user_id: Optional[int]
    task_type: str
    status: str
    title: str
    description: str
    created_at: datetime
    due_at: Optional[datetime]


class TransactionCreate(BaseModel):
    """Create transaction payload."""

    resource_id: int
    action: Literal["borrow", "consume", "replenish", "lost"]
    quantity: int = Field(default=1, ge=1)
    note: str = ""
    borrow_time: Optional[datetime] = None
    expected_return_time: Optional[datetime] = None
    purpose: str = ""
    project_name: str = ""
    estimated_quantity: Optional[int] = Field(default=None, ge=0)
    evidence_url: str = ""
    evidence_type: str = ""
    resource_item_ids: List[int] = Field(default_factory=list)


class ReturnRequest(BaseModel):
    """Return a borrowed device."""

    condition_return: Literal["good", "damaged", "partial_lost"] = "good"
    note: str = ""
    return_time: Optional[datetime] = None
    lost_quantity: int = Field(default=0, ge=0)
    evidence_url: str = ""
    evidence_type: str = ""


class InventoryAdjustmentRequest(BaseModel):
    """Admin direct inventory adjustment payload."""

    target_total_count: int = Field(..., ge=0)
    target_available_count: int = Field(..., ge=0)
    reason: str = Field(..., min_length=1)
    evidence_url: str = ""
    evidence_type: str = ""


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
    project_name: str
    estimated_quantity: Optional[int]
    status: str
    approval_status: str
    approval_id: Optional[int]
    borrow_time: Optional[datetime]
    expected_return_time: Optional[datetime]
    return_time: Optional[datetime]
    duration_minutes: Optional[int]
    condition_return: str
    evidence_url: str
    evidence_type: str
    resource_item_ids: List[int] = Field(default_factory=list)
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


class AgentToolExecution(BaseModel):
    """Executed tool call info."""

    name: str
    status: str
    summary: str


class AgentPendingAction(BaseModel):
    """Pending action that requires explicit confirmation."""

    name: str
    title: str
    confirmation_token: str
    proposed_payload: Dict[str, Any] = Field(default_factory=dict)


class LLMOptions(BaseModel):
    """Per-request LLM runtime overrides provided by the current user."""

    enabled: bool = True
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    timeout: Optional[int] = Field(default=None, ge=5, le=120)


class AgentChatIn(BaseModel):
    """Chat request."""

    message: str
    session_id: Optional[str] = None
    confirm: bool = False
    confirmation_token: Optional[str] = None
    llm_options: Optional[LLMOptions] = None


class AgentChatOut(BaseModel):
    """Chat response."""

    session_id: str
    reply: str
    used_model: bool
    confirmation_required: bool = False
    pending_action: Optional[AgentPendingAction] = None
    executed_tools: List[AgentToolExecution] = Field(default_factory=list)


class ChatMessageOut(ORMBaseModel):
    """Stored chat message."""

    role: str
    content: str
    created_at: datetime


class EnhancedAgentRequest(BaseModel):
    """Enhanced agent payload."""

    question: str
    session_id: Optional[str] = None
    confirm: bool = False
    confirmation_token: Optional[str] = None
    llm_options: Optional[LLMOptions] = None


class EnhancedAgentResponse(BaseModel):
    """Enhanced agent response."""

    session_id: str
    answer: str
    success: bool
    real_time_data: Dict[str, Any] = Field(default_factory=dict)
    confirmation_required: bool = False
    pending_action: Optional[AgentPendingAction] = None
    executed_tools: List[AgentToolExecution] = Field(default_factory=list)


class SchedulerRequest(BaseModel):
    """Scheduling request."""

    resource_id: int
    duration_minutes: int = Field(..., ge=1)
    preferred_start: Optional[datetime] = None


class TimeSlot(BaseModel):
    """Recommended time slot."""

    start: datetime
    end: datetime
    day: str
    hour: int
    score: float
    conflicts: List[Dict[str, Any]] = Field(default_factory=list)


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
    recommendation: str = ""


class DemandPredictionResponse(BaseModel):
    """Demand forecast response."""

    resource_id: int
    days_ahead: int
    predictions: List[DemandPrediction]
    generated_at: datetime
    prediction_method: Optional[str] = None


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

    popular_resources: List[Dict[str, Any]]
    high_utilization_devices: List[Dict[str, Any]]
    analysis_period: str


class UserBehaviorAnalysis(BaseModel):
    """User analytics."""

    top_users: List[Dict[str, Any]]
    user_patterns: List[Dict[str, Any]]


class CostAnalysis(BaseModel):
    """Cost analytics."""

    total_cost: float
    daily_avg_cost: float
    cost_breakdown: List[Dict[str, Any]]
    high_cost_items: List[Dict[str, Any]]


class TrendAnalysis(BaseModel):
    """Trend analytics."""

    daily_usage: List[Dict[str, Any]]
    resource_category_trends: List[Dict[str, Any]]


class AnalyticsRecommendation(BaseModel):
    """Analytics recommendation."""

    type: str
    resource_id: int
    resource_name: str
    message: str
    priority: str


class FairnessMetrics(BaseModel):
    """User fairness metrics."""

    fairness_index: float
    gini_coefficient: float
    top_user_share: float
    active_user_count: int


class OverdueReturnItem(BaseModel):
    """Overdue borrow record."""

    transaction_id: int
    resource_id: int
    resource_name: str
    user_id: int
    user_name: str
    overdue_hours: float
    borrow_time: Optional[datetime]
    expected_return_time: Optional[datetime]


class PrimeTimeMonopolyItem(BaseModel):
    """Prime-time monopoly record."""

    resource_id: int
    resource_name: str
    user_id: int
    user_name: str
    prime_time_hours: float
    prime_time_share: float
    borrow_count: int


class ProjectUsageVarianceItem(BaseModel):
    """Project estimated vs actual usage."""

    project_name: str
    estimated_quantity: int
    actual_quantity: int
    variance: int
    variance_ratio: float


class AnomalyScoreItem(BaseModel):
    """Entity anomaly score."""

    key: str
    name: str
    anomaly_score: float
    reasons: List[str] = Field(default_factory=list)


class AnomalyScoreBreakdown(BaseModel):
    """Grouped anomaly scores."""

    users: List[AnomalyScoreItem] = Field(default_factory=list)
    projects: List[AnomalyScoreItem] = Field(default_factory=list)
    resources: List[AnomalyScoreItem] = Field(default_factory=list)


class ReplenishmentSuggestion(BaseModel):
    """Replenishment suggestion."""

    resource_id: int
    resource_name: str
    current_stock: int
    consumption_rate_per_day: float
    days_to_depletion: Optional[float]
    suggested_replenish_quantity: int
    priority: str
    reason: str


class AnalyticsResponse(BaseModel):
    """Composite analytics response."""

    period: PeriodInfo
    summary: SummaryStats
    resource_analysis: ResourceUsageAnalysis
    user_behavior: UserBehaviorAnalysis
    cost_analysis: CostAnalysis
    trends: TrendAnalysis
    recommendations: List[AnalyticsRecommendation]
    replenishment_suggestions: List[ReplenishmentSuggestion]
    fairness_metrics: FairnessMetrics
    overdue_returns: List[OverdueReturnItem]
    prime_time_monopolies: List[PrimeTimeMonopolyItem]
    project_usage_variance: List[ProjectUsageVarianceItem]
    anomaly_scores: AnomalyScoreBreakdown


class InventoryVisionRequest(BaseModel):
    """Inventory evidence analysis request."""

    resource_id: int
    evidence_url: str
    evidence_type: str = "image"
    ocr_text: str = ""
    observed_count: Optional[int] = Field(default=None, ge=0)


class InventoryVisionResponse(BaseModel):
    """Inventory evidence analysis result."""

    resource_id: int
    resource_name: str
    evidence_url: str
    evidence_type: str
    recognized_count: int
    system_available_count: int
    system_total_count: int
    difference: int
    suggestions: List[str] = Field(default_factory=list)
