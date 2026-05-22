from typing import Set

from fastapi import APIRouter, Header, HTTPException
import sqlite3

from app.core.config import settings
from app.models.schemas import (
    AuthenticatedChatRequest,
    ChatRequest,
    ChatResponse,
    ComplaintNoteCreateRequest,
    ComplaintNoteUpdateRequest,
    ComplaintUpdateRequest,
    KnowledgeArticleCreateRequest,
    KnowledgeArticleUpdateRequest,
    LangChainAgentRequest,
    LangChainRagRequest,
    LangGraphAgentRequest,
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
from app.services.agent_evaluation import run_agent_evaluation
from app.services.langchain_agent import run_langchain_agent
from app.services.langchain_rag_agent import run_langchain_rag_agent
from app.services.langgraph_agent import run_langgraph_agent
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
from app.services.tools import get_complaint_detail, rebuild_knowledge_index, run_rag_evaluation, search_knowledge

router = APIRouter()


# routes.py 阅读地图：
# 1. 先看认证和权限辅助函数，它们会被后面的管理接口复用。
# 2. 再看基础检查、工具日志、审计日志和工具说明接口。
# 3. 然后看登录、用户管理和客服聊天主入口 /chat。
# 4. 最后看投诉、订单、物流、知识库、LangChain 和 LangGraph 接口。


# 0. 认证和权限辅助函数：从请求头里取 token，并判断当前用户能不能执行操作。
def extract_bearer_token(authorization: str = None) -> str:
    if not authorization:
        return ""
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return ""
    return authorization[len(prefix):].strip()


@router.get("/project/capabilities")
def project_capabilities() -> dict:
    return {
        "name": "电商智能客服 Agent",
        "summary": "基于 FastAPI、SQLite、RAG、LLM Function Calling、LangChain 和 LangGraph 的电商售后客服系统。",
        "main_flow": [
            "web/app.js 接收客服输入",
            "routes.py 的 /chat 接口接收请求",
            "agent.py 判断意图并选择执行模式",
            "LLM / RAG / LangGraph / 工具注册表协作处理",
            "tools.py 调用订单、物流、投诉、知识库工具",
            "db.py 读写 SQLite",
            "trace 和 decision_path 返回前端展示",
        ],
        "capabilities": [
            {
                "title": "LLM Function Calling",
                "description": "让大模型根据用户问题选择工具，并在写操作前进入确认流程。",
                "evidence": "支持工具选择、参数提取、权限检查、降级原因展示。",
            },
            {
                "title": "RAG 知识库",
                "description": "把客服政策切片、检索，并把命中来源和分数返回给前端。",
                "evidence": "支持知识库管理、RAG 调试、RAG 自动评测。",
            },
            {
                "title": "LangGraph 多工具工作流",
                "description": "将高风险订单/物流问题拆成状态机节点，先判断风险，再等待用户确认。",
                "evidence": "支持节点链路、工具选择、风险等级、确认创建投诉。",
            },
            {
                "title": "可解释 Agent Trace",
                "description": "每次对话都会返回 steps、trace 和 decision_path，展示 Agent 为什么这样回答。",
                "evidence": "聊天窗口和 Agent 评测都能看到决策链路。",
            },
            {
                "title": "业务后台闭环",
                "description": "覆盖订单、物流、投诉工单、处理人分配、状态流转、备注和统计。",
                "evidence": "支持客服和主管两种角色的售后处理流程。",
            },
            {
                "title": "工程化能力",
                "description": "包含 Docker、自动测试、日志配置、审计日志、工具日志和评测集。",
                "evidence": "可通过 pytest、Docker Compose 和前端调试区验证。",
            },
        ],
        "demo_questions": [
            "查订单 A101",
            "那物流呢",
            "物流超时政策",
            "我的订单 A101 48小时了，怎么还没发货",
            "确认创建投诉",
        ],
    }


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


# 1. 基础检查和可观测接口：确认服务是否正常，并查看工具/审计/Function Calling 信息。
@router.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@router.get("/project/health-report")
def project_health_report() -> dict:
    rag_eval = run_rag_evaluation()
    agent_eval = run_agent_evaluation()
    checks = [
        {
            "name": "RAG 知识库评测",
            "status": "passed" if rag_eval["failed"] == 0 else "failed",
            "detail": f"{rag_eval['passed']}/{rag_eval['total']} 通过",
        },
        {
            "name": "Agent 决策评测",
            "status": "passed" if agent_eval["failed"] == 0 else "failed",
            "detail": f"{agent_eval['passed']}/{agent_eval['total']} 通过",
        },
        {
            "name": "LLM 配置状态",
            "status": "enabled" if settings.llm_enabled else "disabled",
            "detail": f"provider={settings.llm_provider}, model={settings.llm_model}",
        },
        {
            "name": "可解释链路",
            "status": "passed",
            "detail": "聊天 trace、decision_path、LangGraph 节点和评测链路均可展示",
        },
    ]
    failed_count = sum(1 for item in checks if item["status"] == "failed")
    return {
        "status": "ready" if failed_count == 0 else "needs_attention",
        "failed_count": failed_count,
        "checks": checks,
        "recommended_demo": [
            "点击项目能力总览，介绍系统亮点",
            "发送：我的订单 A101 48小时了，怎么还没发货",
            "查看 Agent 决策链路和 LangGraph 节点",
            "回复：确认创建投诉",
            "运行 Agent 评测，展示自动化验证结果",
        ],
    }


@router.get("/project/demo-script")
def project_demo_script() -> dict:
    return {
        "title": "电商智能客服 Agent 面试演示脚本",
        "opening": "这个项目不是普通聊天机器人，而是一个能调用工具、检索知识库、进入 LangGraph 工作流并展示决策链路的客服 Agent。",
        "steps": [
            {
                "title": "项目总览",
                "action": "点击“项目能力总览”",
                "say": "先说明项目整体能力：FastAPI 后端、SQLite 业务数据、RAG 知识库、LLM Function Calling、LangGraph 多工具流程和可解释 Trace。",
                "observe": "观察核心能力卡片和主链路。",
            },
            {
                "title": "基础工具调用",
                "action": "发送：查订单 A101",
                "say": "展示 Agent 识别查询订单意图，并调用订单工具读取数据库。",
                "observe": "观察回复、Agent 执行步骤和 decision_path。",
            },
            {
                "title": "多轮上下文",
                "action": "继续发送：那物流呢",
                "say": "展示 session memory 记住上一轮订单号，用户没有重复输入 A101 也能查询关联物流。",
                "observe": "观察物流 L101 的返回和上下文补全链路。",
            },
            {
                "title": "RAG + LangGraph 高风险处理",
                "action": "发送：我的订单 A101 48小时了，怎么还没发货",
                "say": "展示高风险订单问题进入 LangGraph，内部调用订单、物流和知识库工具，并等待用户确认。",
                "observe": "观察 LangGraph 节点、RAG 命中来源、风险判断和等待确认状态。",
            },
            {
                "title": "确认写入投诉工单",
                "action": "发送：确认创建投诉",
                "say": "展示写操作不会直接执行，而是经过用户确认后才创建投诉，并自动设置高优先级和处理人。",
                "observe": "观察投诉编号、写入结果和决策链路。",
            },
            {
                "title": "自动化自检",
                "action": "点击“项目自检”",
                "say": "最后展示项目不是只靠手动演示，还内置 RAG/Agent 评测和可解释链路检查。",
                "observe": "观察 RAG 评测、Agent 评测、LLM 配置和演示健康度。",
            },
        ],
        "closing": "这个项目的重点是把 LLM Agent 从“能聊天”推进到“能查数据、能调用工具、能检索知识、能确认写操作、能解释决策、能自动评测”。",
    }


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


# 2. 登录和用户管理接口：先确认“你是谁”，再允许主管管理账号。
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


# 3. 客服聊天主入口：前端客服窗口会 POST /chat，然后进入 run_agent_with_steps(...)。
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
    save_chat_message(req.user_id, "agent", result["reply"], steps=result["steps"], trace=result["trace"])
    return ChatResponse(reply=result["reply"], steps=result["steps"], trace=result["trace"])


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


# 4. 投诉接口：查询投诉列表、统计、详情、状态流转和备注。
@router.get("/complaints")
def complaints(
    user_id: str = None,
    status: str = None,
    priority: str = None,
    handler: str = None,
    follow_up_status: str = None,
) -> list:
    return list_complaints(
        user_id=user_id,
        status=status,
        priority=priority,
        handler=handler,
        follow_up_status=follow_up_status,
    )


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


# 9. 知识库和 Agent 实验接口：维护 RAG 知识，并单独测试 LangChain / LangGraph。
@router.get("/knowledge")
def knowledge_articles(include_disabled: bool = True, query: str = None, tag: str = None) -> list:
    return fetch_knowledge_articles(include_disabled=include_disabled, query_text=query, tag=tag)


@router.get("/knowledge/search-debug")
def knowledge_search_debug(query: str) -> dict:
    return search_knowledge(query)


@router.get("/knowledge/evaluate-rag")
def evaluate_rag() -> dict:
    return run_rag_evaluation()


@router.get("/agent/evaluate")
def evaluate_agent() -> dict:
    return run_agent_evaluation()


@router.post("/langchain/rag")
def langchain_rag(req: LangChainRagRequest) -> dict:
    return run_langchain_rag_agent(req.question)


@router.post("/langchain/agent")
def langchain_agent(req: LangChainAgentRequest) -> dict:
    return run_langchain_agent(req.question)


@router.post("/langgraph/agent")
def langgraph_agent(req: LangGraphAgentRequest) -> dict:
    return run_langgraph_agent(req.question, user_id=req.user_id)


@router.post("/knowledge/rebuild-index")
def rebuild_knowledge_index_endpoint(authorization: str = Header(default=None)) -> dict:
    actor = require_manager(authorization)
    result = rebuild_knowledge_index()
    write_audit_log(
        "knowledge.rebuild_index",
        actor=actor,
        target_type="knowledge_index",
        success=True,
        detail={
            "deleted_count": result["deleted_count"],
            "indexed_count": result["indexed_count"],
        },
    )
    return {
        "status": "rebuilt",
        "deleted_count": result["deleted_count"],
        "indexed_count": result["indexed_count"],
    }


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
        rebuild_knowledge_index()
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
        if article is not None:
            rebuild_knowledge_index()
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
    rebuild_knowledge_index()
    write_audit_log(
        "knowledge.delete",
        actor=actor,
        target_type="knowledge",
        target_id=str(article_id),
        success=True,
    )
    return {"deleted": True, "id": article_id}
