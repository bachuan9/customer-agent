from pydantic import BaseModel


class ChatRequest(BaseModel):
    user_id: str
    message: str
    role: str = "agent"


class ChatResponse(BaseModel):
    reply: str


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
