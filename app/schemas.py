"""Pydantic 请求/响应模型。"""

from datetime import datetime
from typing import Optional

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
