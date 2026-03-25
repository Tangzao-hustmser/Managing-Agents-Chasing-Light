"""Pydantic 请求/响应模型。"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class UserBase(BaseModel):
    """用户公共字段。"""

    username: str = Field(..., description="用户名")
    real_name: str = Field(..., description="真实姓名")
    student_id: str = Field(..., description="学号/工号")
    email: Optional[str] = None
    role: str = Field(default="student", description="角色：student/admin/teacher")


class UserCreate(UserBase):
    """用户注册。"""

    password: str = Field(..., description="密码")


class UserLogin(BaseModel):
    """用户登录。"""

    username: str
    password: str


class UserOut(UserBase):
    """用户响应。"""

    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ResourceBase(BaseModel):
    """资源公共字段。"""

    name: str = Field(..., description="资源名称")
    category: str = Field(..., description="资源类别：device 或 material")
    subtype: str = Field(..., description="资源子类：3D打印机、开发板等")
    location: str = "创新实践基地"
    total_count: int = 1
    available_count: int = 1
    unit_cost: float = 0.0
    min_threshold: int = 1
    status: str = "active"
    description: str = ""


class ResourceCreate(ResourceBase):
    """创建资源请求。"""


class ResourceUpdate(BaseModel):
    """更新资源请求，字段全部可选。"""

    name: Optional[str] = None
    location: Optional[str] = None
    total_count: Optional[int] = None
    available_count: Optional[int] = None
    unit_cost: Optional[float] = None
    min_threshold: Optional[int] = None
    status: Optional[str] = None
    description: Optional[str] = None


class ResourceOut(ResourceBase):
    """资源响应。"""

    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TransactionCreate(BaseModel):
    """新建流水请求。"""

    resource_id: int
    action: str = Field(..., description="borrow/return/consume/replenish/lost")
    quantity: int = 1
    note: str = ""
    
    # 时间维度（借用必填）
    borrow_time: Optional[datetime] = None
    expected_return_time: Optional[datetime] = None
    
    # 借还细节
    purpose: str = ""
    condition_return: str = "完好"


class TransactionOut(BaseModel):
    """流水响应。"""

    id: int
    resource_id: int
    user_id: int
    action: str
    quantity: int
    note: str
    borrow_time: Optional[datetime]
    return_time: Optional[datetime]
    expected_return_time: Optional[datetime]
    duration_minutes: Optional[int]
    purpose: str
    condition_return: str
    is_approved: bool
    approval_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class AlertOut(BaseModel):
    """预警响应。"""

    id: int
    level: str
    type: str
    message: str
    created_at: datetime

    class Config:
        from_attributes = True


class ApprovalTaskOut(BaseModel):
    """审批任务响应。"""

    id: int
    transaction_id: int
    requester_id: int
    approver_id: Optional[int]
    status: str
    reason: str
    created_at: datetime
    approved_at: Optional[datetime]

    class Config:
        from_attributes = True


class ApprovalTaskApprove(BaseModel):
    """审批任务审批请求。"""

    approved: bool = Field(..., description="是否批准")
    reason: str = Field(default="", description="批准或拒绝理由")


class AgentAskIn(BaseModel):
    """智能体问答输入。"""

    question: str = Field(..., description="用户自然语言问题")


class AgentAskOut(BaseModel):
    """智能体问答输出。"""

    intent: str
    answer: str


class AgentChatIn(BaseModel):
    """对话式智能体输入。"""

    message: str = Field(..., description="用户输入")
    session_id: Optional[str] = Field(default=None, description="会话 ID，不传则自动创建")


class AgentChatOut(BaseModel):
    """对话式智能体输出。"""

    session_id: str
    reply: str
    used_model: bool


class ChatMessageOut(BaseModel):
    """会话历史消息。"""

    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class EnhancedAgentRequest(BaseModel):
    """增强版智能体请求。"""
    
    question: str = Field(..., description="用户问题")
    session_id: Optional[str] = Field(default="default", description="会话ID，用于多轮对话")


class EnhancedAgentResponse(BaseModel):
    """增强版智能体响应。"""
    
    session_id: str = Field(..., description="会话ID")
    answer: str = Field(..., description="智能体回答")
    success: bool = Field(..., description="是否成功使用LLM")
    real_time_data: dict = Field(..., description="实时数据上下文")


class SchedulerRequest(BaseModel):
    """智能调度请求。"""
    
    resource_id: int = Field(..., description="资源ID")
    duration_minutes: int = Field(..., description="使用时长（分钟）")
    preferred_start: Optional[datetime] = Field(default=None, description="偏好开始时间")


class TimeSlot(BaseModel):
    """时段信息。"""
    
    start: datetime = Field(..., description="开始时间")
    end: datetime = Field(..., description="结束时间")
    day: str = Field(..., description="日期")
    hour: int = Field(..., description="小时")
    score: float = Field(..., description="评分（0-100）")
    conflicts: List[Dict] = Field(default_factory=list, description="冲突信息")


class SchedulerResponse(BaseModel):
    """智能调度响应。"""
    
    resource_id: int = Field(..., description="资源ID")
    duration_minutes: int = Field(..., description="使用时长（分钟）")
    optimal_slots: List[TimeSlot] = Field(..., description="最优时段推荐")
    generated_at: datetime = Field(..., description="生成时间")


class DemandPrediction(BaseModel):
    """需求预测结果。"""
    
    date: str = Field(..., description="预测日期")
    predicted_demand: float = Field(..., description="预测需求")
    confidence: float = Field(..., description="置信度")
    recommendation: str = Field(..., description="建议")


class DemandPredictionResponse(BaseModel):
    """需求预测响应。"""
    
    resource_id: int = Field(..., description="资源ID")
    days_ahead: int = Field(..., description="预测天数")
    predictions: List[DemandPrediction] = Field(..., description="预测结果")
    generated_at: datetime = Field(..., description="生成时间")


class OptimizationRecommendation(BaseModel):
    """优化建议。"""
    
    resource_id: int = Field(..., description="资源ID")
    resource_name: str = Field(..., description="资源名称")
    utilization: float = Field(..., description="利用率")
    recommendation: str = Field(..., description="优化建议")
    priority: str = Field(..., description="优先级")


class OptimizationResponse(BaseModel):
    """资源优化响应。"""
    
    total_devices: int = Field(..., description="设备总数")
    recommendations: List[OptimizationRecommendation] = Field(..., description="优化建议")
    generated_at: datetime = Field(..., description="生成时间")


class PeriodInfo(BaseModel):
    """分析时间段信息。"""
    
    start_date: str = Field(..., description="开始日期")
    end_date: str = Field(..., description="结束日期")
    days: int = Field(..., description="天数")


class SummaryStats(BaseModel):
    """基础统计信息。"""
    
    total_transactions: int = Field(..., description="总交易量")
    active_users: int = Field(..., description="活跃用户数")
    average_device_utilization: float = Field(..., description="平均设备利用率")
    material_consumption: int = Field(..., description="物料消耗量")
    daily_avg_transactions: float = Field(..., description="日均交易量")


class ResourceUsageAnalysis(BaseModel):
    """资源使用分析。"""
    
    popular_resources: List[Dict] = Field(..., description="热门资源")
    high_utilization_devices: List[Dict] = Field(..., description="高利用率设备")
    analysis_period: str = Field(..., description="分析周期")


class UserBehaviorAnalysis(BaseModel):
    """用户行为分析。"""
    
    top_users: List[Dict] = Field(..., description="活跃用户排行榜")
    user_patterns: List[Dict] = Field(..., description="用户行为模式")


class CostAnalysis(BaseModel):
    """成本分析。"""
    
    total_cost: float = Field(..., description="总成本")
    daily_avg_cost: float = Field(..., description="日均成本")
    cost_breakdown: List[Dict] = Field(..., description="成本明细")
    high_cost_items: List[Dict] = Field(..., description="高成本项目")


class TrendAnalysis(BaseModel):
    """趋势分析。"""
    
    daily_usage: List[Dict] = Field(..., description="日使用趋势")
    resource_category_trends: List[Dict] = Field(..., description="资源类别趋势")


class AnalyticsRecommendation(BaseModel):
    """分析建议。"""
    
    type: str = Field(..., description="建议类型")
    resource_id: int = Field(..., description="资源ID")
    resource_name: str = Field(..., description="资源名称")
    message: str = Field(..., description="建议内容")
    priority: str = Field(..., description="优先级")


class AnalyticsResponse(BaseModel):
    """综合数据分析响应。"""
    
    period: PeriodInfo = Field(..., description="分析周期")
    summary: SummaryStats = Field(..., description="基础统计")
    resource_analysis: ResourceUsageAnalysis = Field(..., description="资源使用分析")
    user_behavior: UserBehaviorAnalysis = Field(..., description="用户行为分析")
    cost_analysis: CostAnalysis = Field(..., description="成本分析")
    trends: TrendAnalysis = Field(..., description="趋势分析")
    recommendations: List[AnalyticsRecommendation] = Field(..., description="优化建议")
