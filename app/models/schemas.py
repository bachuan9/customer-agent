from typing import Any, Dict, List

from pydantic import BaseModel


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
