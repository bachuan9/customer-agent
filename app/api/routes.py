from typing import Set

from fastapi import APIRouter, Header, HTTPException
import sqlite3

from app.models.schemas import (
    AuthenticatedChatRequest,
    ChatRequest,
    ChatResponse,
    ComplaintNoteCreateRequest,
    ComplaintNoteUpdateRequest,
    ComplaintUpdateRequest,
    KnowledgeArticleCreateRequest,
    KnowledgeArticleUpdateRequest,
    LoginRequest,
    LogisticsCreateRequest,
    LogisticsUpdateRequest,
    ManualChatReplyRequest,
    OrderCreateRequest,
    OrderUpdateRequest,
    UserActiveUpdateRequest,
    UserCreateRequest,
    UserPasswordResetRequest,
    UserRoleUpdateRequest,
)
from app.services.agent import list_complaints, run_agent_with_steps
from app.services.tool_registry import list_function_calling_tools
from app.storage.db import (
    ALLOWED_LOGISTICS_STATUSES,
    ALLOWED_ORDER_STATUSES,
    ALLOWED_USER_ROLES,
    clear_chat_messages,
    clear_session_messages,
    delete_complaint_note,
    fetch_audit_log_stats,
    fetch_audit_logs,
    fetch_chat_messages,
    fetch_chat_sessions,
    fetch_logistics,
    fetch_orders,
    fetch_complaint_notes,
    fetch_complaint_stats,
    fetch_knowledge_articles,
    fetch_tool_call_stats,
    fetch_tool_call_logs,
    fetch_users,
    get_complaint_by_id,
    get_knowledge_article,
    get_logistics_status,
    get_order_status,
    get_user_by_token,
    insert_knowledge_article,
    insert_user,
    insert_order,
    insert_logistics,
    insert_complaint_note,
    insert_audit_log,
    login_user,
    logout_user_by_token,
    reset_user_password,
    save_chat_message,
    delete_knowledge_article,
    update_complaint,
    update_complaint_note,
    update_knowledge_article,
    update_logistics_status,
    update_order_status,
    update_user_active,
    update_user_role,
)
from app.services.tools import get_complaint_detail, search_knowledge

router = APIRouter()


def extract_bearer_token(authorization: str = None) -> str:
    if not authorization:
        return ""
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return ""
    return authorization[len(prefix):].strip()


def get_current_user_from_header(authorization: str = None) -> dict:
    token = extract_bearer_token(authorization)
    user = get_user_by_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid or missing token")
    return user


def require_role(authorization: str = None, allowed_roles: Set[str] = None) -> dict:
    user = get_current_user_from_header(authorization)
    roles = allowed_roles or set()
    if user["role"] not in roles:
        required = ", ".join(sorted(roles)) or "none"
        raise HTTPException(status_code=403, detail=f"required role: {required}")
    return user


def require_manager(authorization: str = None) -> dict:
    return require_role(authorization, {"manager"})


def ensure_chat_history_access(user_id: str, authorization: str = None) -> None:
    token = extract_bearer_token(authorization)
    if not token:
        return

    user = get_user_by_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid or missing token")
    if user["role"] == "manager" or user["username"] == user_id:
        return
    raise HTTPException(status_code=403, detail="cannot access another user's chat history")


def write_audit_log(
    action: str,
    actor: dict = None,
    target_type: str = None,
    target_id: str = None,
    success: bool = True,
    detail: dict = None,
) -> None:
    insert_audit_log(
        action=action,
        actor_username=actor["username"] if actor else None,
        actor_role=actor["role"] if actor else None,
        target_type=target_type,
        target_id=target_id,
        success=success,
        detail=detail,
    )


# 1. 基础检查接口：用来确认后端服务是否正常运行。
@router.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@router.get("/tool-logs")
def tool_logs(limit: int = 20, source: str = None, success: bool = None) -> list:
    return fetch_tool_call_logs(limit=limit, source=source, success=success)


@router.get("/tool-logs/stats")
def tool_log_stats() -> dict:
    return fetch_tool_call_stats()


@router.get("/audit-logs")
def audit_logs(
    limit: int = 50,
    action: str = None,
    success: bool = None,
    actor: str = None,
    authorization: str = Header(default=None),
) -> list:
    require_manager(authorization)
    return fetch_audit_logs(limit=limit, action=action, success=success, actor_username=actor)


@router.get("/audit-logs/stats")
def audit_log_stats(authorization: str = Header(default=None)) -> dict:
    require_manager(authorization)
    return fetch_audit_log_stats()


@router.get("/tools/function-calling")
def function_calling_tools() -> list:
    return list_function_calling_tools()


# 2. 登录接口：先确认“你是谁”，后续权限才有依据。
@router.post("/auth/login")
def login(req: LoginRequest) -> dict:
    result = login_user(req.username, req.password)
    if result is None:
        write_audit_log(
            "auth.login_failed",
            target_type="user",
            target_id=req.username,
            success=False,
            detail={"reason": "invalid username, password, or disabled user"},
        )
        raise HTTPException(status_code=401, detail="invalid username or password")
    write_audit_log(
        "auth.login_success",
        actor=result["user"],
        target_type="user",
        target_id=result["user"]["username"],
        success=True,
    )
    return result


@router.get("/auth/me")
def auth_me(authorization: str = Header(default=None)) -> dict:
    user = get_current_user_from_header(authorization)
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
    }


@router.post("/auth/logout")
def logout(authorization: str = Header(default=None)) -> dict:
    token = extract_bearer_token(authorization)
    user = get_user_by_token(token)
    logged_out = logout_user_by_token(token)
    if not logged_out:
        write_audit_log("auth.logout_failed", actor=user, success=False)
        raise HTTPException(status_code=401, detail="invalid or missing token")
    write_audit_log("auth.logout", actor=user, target_type="user", target_id=user["username"] if user else None)
    return {"logged_out": True}


@router.get("/users")
def users(authorization: str = Header(default=None)) -> list:
    require_manager(authorization)
    return fetch_users()


@router.post("/users")
def create_user(req: UserCreateRequest, authorization: str = Header(default=None)) -> dict:
    actor = require_manager(authorization)
    if req.role not in ALLOWED_USER_ROLES:
        write_audit_log(
            "user.create",
            actor=actor,
            target_type="user",
            target_id=req.username,
            success=False,
            detail={"reason": "invalid user role", "role": req.role},
        )
        raise HTTPException(status_code=400, detail="invalid user role")

    try:
        user = insert_user(req.username, req.password, req.display_name, req.role)
        write_audit_log(
            "user.create",
            actor=actor,
            target_type="user",
            target_id=req.username,
            success=True,
            detail={"role": req.role},
        )
        return user
    except sqlite3.IntegrityError:
        write_audit_log(
            "user.create",
            actor=actor,
            target_type="user",
            target_id=req.username,
            success=False,
            detail={"reason": "user already exists"},
        )
        raise HTTPException(status_code=409, detail="user already exists")


@router.patch("/users/{username}/role")
def update_user_role_endpoint(
    username: str,
    req: UserRoleUpdateRequest,
    authorization: str = Header(default=None),
) -> dict:
    actor = require_manager(authorization)
    if req.role not in ALLOWED_USER_ROLES:
        write_audit_log(
            "user.update_role",
            actor=actor,
            target_type="user",
            target_id=username,
            success=False,
            detail={"reason": "invalid user role", "role": req.role},
        )
        raise HTTPException(status_code=400, detail="invalid user role")

    user = update_user_role(username, req.role)
    if user is None:
        write_audit_log(
            "user.update_role",
            actor=actor,
            target_type="user",
            target_id=username,
            success=False,
            detail={"reason": "user not found", "role": req.role},
        )
        raise HTTPException(status_code=404, detail="user not found")
    write_audit_log(
        "user.update_role",
        actor=actor,
        target_type="user",
        target_id=username,
        success=True,
        detail={"role": req.role},
    )
    return user


@router.patch("/users/{username}/active")
def update_user_active_endpoint(
    username: str,
    req: UserActiveUpdateRequest,
    authorization: str = Header(default=None),
) -> dict:
    actor = require_manager(authorization)
    user = update_user_active(username, req.is_active)
    if user is None:
        write_audit_log(
            "user.update_active",
            actor=actor,
            target_type="user",
            target_id=username,
            success=False,
            detail={"reason": "user not found", "is_active": req.is_active},
        )
        raise HTTPException(status_code=404, detail="user not found")
    write_audit_log(
        "user.update_active",
        actor=actor,
        target_type="user",
        target_id=username,
        success=True,
        detail={"is_active": req.is_active},
    )
    return user


@router.patch("/users/{username}/password")
def reset_user_password_endpoint(
    username: str,
    req: UserPasswordResetRequest,
    authorization: str = Header(default=None),
) -> dict:
    actor = require_manager(authorization)
    if not req.password:
        write_audit_log(
            "user.reset_password",
            actor=actor,
            target_type="user",
            target_id=username,
            success=False,
            detail={"reason": "password is required"},
        )
        raise HTTPException(status_code=400, detail="password is required")

    user = reset_user_password(username, req.password)
    if user is None:
        write_audit_log(
            "user.reset_password",
            actor=actor,
            target_type="user",
            target_id=username,
            success=False,
            detail={"reason": "user not found"},
        )
        raise HTTPException(status_code=404, detail="user not found")
    write_audit_log(
        "user.reset_password",
        actor=actor,
        target_type="user",
        target_id=username,
        success=True,
    )
    return user


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, authorization: str = Header(default=None)) -> ChatResponse:
    token = extract_bearer_token(authorization)
    user = get_user_by_token(token)
    if user is not None:
        req = AuthenticatedChatRequest(
            user_id=user["username"],
            username=user["username"],
            display_name=user["display_name"],
            role=user["role"],
            message=req.message,
        )

    result = run_agent_with_steps(req)
    save_chat_message(req.user_id, "user", req.message)
    save_chat_message(req.user_id, "agent", result["reply"], steps=result["steps"])
    return ChatResponse(reply=result["reply"], steps=result["steps"])


@router.get("/chat/sessions")
def chat_sessions(limit: int = 50, authorization: str = Header(default=None)) -> list:
    user = get_user_by_token(extract_bearer_token(authorization))
    if user is not None and user["role"] != "manager":
        return [session for session in fetch_chat_sessions(limit=limit) if session["user_id"] == user["username"]]
    return fetch_chat_sessions(limit=limit)


@router.get("/chat/history/{user_id}")
def chat_history(user_id: str, limit: int = 50, authorization: str = Header(default=None)) -> list:
    ensure_chat_history_access(user_id, authorization)
    return fetch_chat_messages(user_id, limit=limit)


@router.post("/chat/history/{user_id}/reply")
def reply_to_chat_history(
    user_id: str,
    req: ManualChatReplyRequest,
    authorization: str = Header(default=None),
) -> dict:
    ensure_chat_history_access(user_id, authorization)
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="reply message is required")

    return save_chat_message(
        user_id=user_id,
        sender="agent",
        message=message,
        steps=["人工客服回复：保存到聊天历史"],
    )


@router.delete("/chat/history/{user_id}")
def delete_chat_history(user_id: str, authorization: str = Header(default=None)) -> dict:
    ensure_chat_history_access(user_id, authorization)
    deleted = clear_chat_messages(user_id)
    clear_session_messages(user_id)
    return {"deleted": deleted, "session_cleared": True}


# 4. 投诉列表接口：支持按 user_id、status、priority、handler 筛选投诉。
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


# 5. 订单接口：查询、列表、新建订单。
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


# 6. 物流接口：查询、列表、新建物流。
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


# 7. 订单和物流更新接口：普通 REST API 的 PATCH 更新入口。
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


# 8. 投诉更新接口：普通 REST API 修改 status、priority、handler。
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


# 9. 投诉备注接口：添加、查询、删除某条投诉备注。
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


# 10. 知识库管理接口：让前端可以维护 Agent 会检索的客服政策。
@router.get("/knowledge")
def knowledge_articles(include_disabled: bool = True, query: str = None, tag: str = None) -> list:
    return fetch_knowledge_articles(include_disabled=include_disabled, query_text=query, tag=tag)


@router.get("/knowledge/search-debug")
def knowledge_search_debug(query: str) -> dict:
    return search_knowledge(query)


@router.get("/knowledge/{article_id}")
def knowledge_article_detail(article_id: int) -> dict:
    article = get_knowledge_article(article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="knowledge article not found")
    return article


@router.post("/knowledge")
def create_knowledge_article(req: KnowledgeArticleCreateRequest, authorization: str = Header(default=None)) -> dict:
    actor = require_manager(authorization)
    try:
        article = insert_knowledge_article(req.title, req.content, req.tags, req.enabled)
        write_audit_log(
            "knowledge.create",
            actor=actor,
            target_type="knowledge",
            target_id=str(article["id"]),
            success=True,
            detail={"title": req.title, "enabled": req.enabled},
        )
        return article
    except ValueError as exc:
        write_audit_log(
            "knowledge.create",
            actor=actor,
            target_type="knowledge",
            success=False,
            detail={"reason": str(exc), "title": req.title},
        )
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/knowledge/{article_id}")
def update_knowledge_article_endpoint(
    article_id: int,
    req: KnowledgeArticleUpdateRequest,
    authorization: str = Header(default=None),
) -> dict:
    actor = require_manager(authorization)
    if req.title is None and req.content is None and req.tags is None and req.enabled is None:
        write_audit_log(
            "knowledge.update",
            actor=actor,
            target_type="knowledge",
            target_id=str(article_id),
            success=False,
            detail={"reason": "empty update"},
        )
        raise HTTPException(status_code=400, detail="title, content, tags or enabled is required")

    try:
        article = update_knowledge_article(
            article_id,
            title=req.title,
            content=req.content,
            tags=req.tags,
            enabled=req.enabled,
        )
    except ValueError as exc:
        write_audit_log(
            "knowledge.update",
            actor=actor,
            target_type="knowledge",
            target_id=str(article_id),
            success=False,
            detail={"reason": str(exc)},
        )
        raise HTTPException(status_code=400, detail=str(exc))

    if article is None:
        write_audit_log(
            "knowledge.update",
            actor=actor,
            target_type="knowledge",
            target_id=str(article_id),
            success=False,
            detail={"reason": "knowledge article not found"},
        )
        raise HTTPException(status_code=404, detail="knowledge article not found")
    write_audit_log(
        "knowledge.update",
        actor=actor,
        target_type="knowledge",
        target_id=str(article_id),
        success=True,
        detail={
            "title_changed": req.title is not None,
            "content_changed": req.content is not None,
            "tags_changed": req.tags is not None,
            "enabled_changed": req.enabled is not None,
        },
    )
    return article


@router.delete("/knowledge/{article_id}")
def delete_knowledge_article_endpoint(article_id: int, authorization: str = Header(default=None)) -> dict:
    actor = require_manager(authorization)
    deleted = delete_knowledge_article(article_id)
    if not deleted:
        write_audit_log(
            "knowledge.delete",
            actor=actor,
            target_type="knowledge",
            target_id=str(article_id),
            success=False,
            detail={"reason": "knowledge article not found"},
        )
        raise HTTPException(status_code=404, detail="knowledge article not found")
    write_audit_log(
        "knowledge.delete",
        actor=actor,
        target_type="knowledge",
        target_id=str(article_id),
        success=True,
    )
    return {"deleted": True, "id": article_id}
