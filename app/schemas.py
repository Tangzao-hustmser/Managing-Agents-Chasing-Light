"""Pydantic 请求/响应模型。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


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
    user_name: str
    action: str = Field(..., description="borrow/return/consume/replenish/lost")
    quantity: int = 1
    note: str = ""


class TransactionOut(TransactionCreate):
    """流水响应。"""

    id: int
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
