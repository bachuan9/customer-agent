from typing import Any, Dict, List

from pydantic import BaseModel


# schemas.py 阅读地图：
# 1. ChatRequest / ChatResponse：客服窗口 /chat 的请求和响应。
# 2. Login / User：登录、用户管理、RBAC 权限相关请求。
# 3. Complaint / Order / Logistics：投诉、订单、物流接口请求。
# 4. Knowledge / LangChain / LangGraph：知识库和 Agent 实验接口请求。


# 1. 客服聊天接口：前端客服窗口会使用这些模型。
class ChatRequest(BaseModel):
    user_id: str
    message: str
    role: str = "agent"


class AuthenticatedChatRequest(ChatRequest):
    username: str = None
    display_name: str = None


class ChatResponse(BaseModel):
    reply: str
    steps: List[str] = []
    trace: Dict[str, Any] = {}


class ManualChatReplyRequest(BaseModel):
    message: str


# 2. 登录和用户管理接口：认证、账号、角色、启用状态和重置密码。
class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreateRequest(BaseModel):
    username: str
    password: str
    display_name: str
    role: str = "agent"


class UserRoleUpdateRequest(BaseModel):
    role: str


class UserActiveUpdateRequest(BaseModel):
    is_active: bool


class UserPasswordResetRequest(BaseModel):
    password: str


# 3. 投诉、订单、物流接口：普通 REST API 的请求体。
class ComplaintUpdateRequest(BaseModel):
    status: str = None
    priority: str = None
    handler: str = None


class ComplaintNoteCreateRequest(BaseModel):
    content: str
    author: str = "客服"


class ComplaintNoteUpdateRequest(BaseModel):
    content: str


class OrderUpdateRequest(BaseModel):
    status: str


class OrderCreateRequest(BaseModel):
    order_no: str
    user_id: str
    status: str = "pending"


class LogisticsUpdateRequest(BaseModel):
    status: str


class LogisticsCreateRequest(BaseModel):
    tracking_no: str
    order_no: str
    status: str = "pending"


# 4. 知识库和 Agent 实验接口：RAG、LangChain、LangGraph 使用。
class KnowledgeArticleCreateRequest(BaseModel):
    title: str
    content: str
    tags: str = ""
    enabled: bool = True


class KnowledgeArticleUpdateRequest(BaseModel):
    title: str = None
    content: str = None
    tags: str = None
    enabled: bool = None


class LangChainRagRequest(BaseModel):
    question: str


class LangChainAgentRequest(BaseModel):
    question: str


class LangGraphAgentRequest(BaseModel):
    question: str
    user_id: str = "anonymous"
