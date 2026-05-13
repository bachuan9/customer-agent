from fastapi import APIRouter, HTTPException
import sqlite3

from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    ComplaintNoteCreateRequest,
    ComplaintNoteUpdateRequest,
    ComplaintUpdateRequest,
    LogisticsCreateRequest,
    LogisticsUpdateRequest,
    OrderCreateRequest,
    OrderUpdateRequest,
)
from app.services.agent import list_complaints, run_agent
from app.services.tool_registry import list_function_calling_tools
from app.storage.db import (
    ALLOWED_LOGISTICS_STATUSES,
    ALLOWED_ORDER_STATUSES,
    delete_complaint_note,
    fetch_logistics,
    fetch_orders,
    fetch_complaint_notes,
    fetch_complaint_stats,
    fetch_tool_call_stats,
    fetch_tool_call_logs,
    get_complaint_by_id,
    get_logistics_status,
    get_order_status,
    insert_order,
    insert_logistics,
    insert_complaint_note,
    update_complaint,
    update_complaint_note,
    update_logistics_status,
    update_order_status,
)
from app.services.tools import get_complaint_detail

router = APIRouter()


# 1. 基础检查接口：用来确认后端服务是否正常运行。
@router.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@router.get("/tool-logs")
def tool_logs(limit: int = 20) -> list:
    return fetch_tool_call_logs(limit)


@router.get("/tool-logs/stats")
def tool_log_stats() -> dict:
    return fetch_tool_call_stats()


@router.get("/tools/function-calling")
def function_calling_tools() -> list:
    return list_function_calling_tools()


# 2. Agent 聊天接口：前端聊天框发来的消息会进入这里。
@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    reply = run_agent(req)
    return ChatResponse(reply=reply)


# 3. 投诉列表接口：支持按 user_id、status、priority、handler 筛选投诉。
@router.get("/complaints")
def complaints(
    user_id: str = None,
    status: str = None,
    priority: str = None,
    handler: str = None,
) -> list:
    return list_complaints(user_id=user_id, status=status, priority=priority, handler=handler)


@router.get("/complaints/stats")
def complaint_stats() -> dict:
    return fetch_complaint_stats()


# 4. 订单接口：查询、列表、新建订单。
@router.get("/orders/{order_no}")
def order_status(order_no: str) -> dict:
    status = get_order_status(order_no)
    if status is None:
        raise HTTPException(status_code=404, detail="order not found")
    return {"order_no": order_no, "status": status}


@router.get("/orders")
def order_list() -> list:
    return fetch_orders()


@router.post("/orders")
def create_order(req: OrderCreateRequest) -> dict:
    if req.status not in ALLOWED_ORDER_STATUSES:
        raise HTTPException(status_code=400, detail="invalid order status")
    try:
        return insert_order(req.order_no, req.user_id, req.status)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="order already exists")


# 5. 物流接口：查询、列表、新建物流。
@router.get("/logistics/{tracking_no}")
def logistics_status(tracking_no: str) -> dict:
    status = get_logistics_status(tracking_no)
    if status is None:
        raise HTTPException(status_code=404, detail="logistics not found")
    return {"tracking_no": tracking_no, "status": status}


@router.get("/logistics")
def logistics_list() -> list:
    return fetch_logistics()


@router.post("/logistics")
def create_logistics(req: LogisticsCreateRequest) -> dict:
    if req.status not in ALLOWED_LOGISTICS_STATUSES:
        raise HTTPException(status_code=400, detail="invalid logistics status")
    try:
        insert_logistics(req.tracking_no, req.order_no, req.status)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="logistics already exists")
    return {
        "tracking_no": req.tracking_no,
        "order_no": req.order_no,
        "status": req.status,
    }


# 6. 订单和物流更新接口：普通 REST API 的 PATCH 更新入口。
@router.patch("/orders/{order_no}")
def update_order(order_no: str, req: OrderUpdateRequest) -> dict:
    if req.status not in ALLOWED_ORDER_STATUSES:
        raise HTTPException(status_code=400, detail="invalid order status")

    updated = update_order_status(order_no, req.status)
    if not updated:
        raise HTTPException(status_code=404, detail="order not found")

    return {"order_no": order_no, "status": req.status}


@router.patch("/logistics/{tracking_no}")
def update_logistics(tracking_no: str, req: LogisticsUpdateRequest) -> dict:
    if req.status not in ALLOWED_LOGISTICS_STATUSES:
        raise HTTPException(status_code=400, detail="invalid logistics status")

    updated = update_logistics_status(tracking_no, req.status)
    if not updated:
        raise HTTPException(status_code=404, detail="logistics not found")

    return {"tracking_no": tracking_no, "status": req.status}


# 7. 投诉更新接口：普通 REST API 修改 status、priority、handler。
@router.get("/complaints/{complaint_id}")
def complaint_detail(complaint_id: str) -> dict:
    detail = get_complaint_detail(complaint_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="complaint not found")
    return detail


@router.patch("/complaints/{complaint_id}")
def update_complaint_endpoint(complaint_id: str, req: ComplaintUpdateRequest) -> dict:
    if req.status is None and req.priority is None and req.handler is None:
        raise HTTPException(status_code=400, detail="status, priority or handler is required")

    complaint = get_complaint_by_id(complaint_id)
    if complaint is None:
        raise HTTPException(status_code=404, detail="complaint not found")

    try:
        updated = update_complaint(
            complaint_id,
            status=req.status,
            priority=req.priority,
            handler=req.handler,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return updated


# 8. 投诉备注接口：添加、查询、删除某条投诉备注。
@router.post("/complaints/{complaint_id}/notes")
def create_complaint_note(complaint_id: str, req: ComplaintNoteCreateRequest) -> dict:
    try:
        note = insert_complaint_note(complaint_id, req.content, req.author)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if note is None:
        raise HTTPException(status_code=404, detail="complaint not found")
    return note


@router.get("/complaints/{complaint_id}/notes")
def complaint_notes(complaint_id: str) -> list:
    notes = fetch_complaint_notes(complaint_id)
    if notes is None:
        raise HTTPException(status_code=404, detail="complaint not found")
    return notes


@router.patch("/complaint-notes/{note_id}")
def update_note(note_id: str, req: ComplaintNoteUpdateRequest) -> dict:
    try:
        note = update_complaint_note(note_id, req.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if note is None:
        raise HTTPException(status_code=404, detail="complaint note not found")
    return note


@router.delete("/complaint-notes/{note_id}")
def delete_note(note_id: str) -> dict:
    deleted = delete_complaint_note(note_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="complaint note not found")
    return {"deleted": True, "note_id": note_id}
