import re
from typing import Any, Dict, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.services.langchain_agent import select_tool_with_llm_fallback
from app.services.langchain_rag_agent import run_langchain_rag_agent
from app.services.langchain_tools import list_langchain_tools
from app.services.tools import create_complaint, handle_logistics_issue, handle_order_issue
from app.storage.database_session import DatabaseSessionStore


HIGH_RISK_KEYWORDS = ["48小时", "48 小时", "超时", "投诉", "破损", "赔付", "升级"]
CONFIRM_CREATE_COMPLAINT_MESSAGES = ["确认创建投诉", "确认", "创建投诉", "同意创建投诉"]
PENDING_CONFIRMATION_TYPE = "langgraph_pending_confirmation"
PENDING_CONFIRMATION_RESOLVED_TYPE = "langgraph_pending_confirmation_resolved"
SESSION_STORE = DatabaseSessionStore()
ORDER_NO_PATTERN = re.compile(r"\bA\d+\b", re.IGNORECASE)
TRACKING_NO_PATTERN = re.compile(r"\bL\d+\b", re.IGNORECASE)


class LangGraphAgentState(TypedDict, total=False):
    question: str
    user_id: str
    pending_confirmation: Optional[Dict[str, Any]]
    is_confirm_message: bool
    selection: Dict[str, Any]
    reply: str
    trace: Dict[str, Any]
    tool_result: Optional[Dict[str, Any]]
    created_complaint: Optional[Dict[str, Any]]


# 1. 入口函数：外部调用 LangGraph Agent 时，先从这里进入。
def run_langgraph_agent(question: str, user_id: str = "anonymous") -> Dict[str, Any]:
    workflow = build_langgraph_workflow()
    final_state = workflow.invoke({"question": question, "user_id": user_id})
    return {
        "question": final_state["question"],
        "user_id": final_state["user_id"],
        "reply": final_state["reply"],
        "trace": final_state["trace"],
        "tool_result": final_state.get("tool_result"),
        "created_complaint": final_state.get("created_complaint"),
    }


# 2. 流程编排：这里决定 LangGraph 每一步怎么走。
def build_langgraph_workflow():
    graph = StateGraph(LangGraphAgentState)

    graph.add_node("check_pending_confirmation", check_pending_confirmation_node)
    graph.add_node("create_complaint", create_complaint_node)
    graph.add_node("select_tool", select_tool_node)
    graph.add_node("call_tool", call_tool_node)
    graph.add_node("assess_risk", assess_risk_node)
    graph.add_node("confirm_complaint", confirm_complaint_node)
    graph.add_node("no_tool_reply", no_tool_reply_node)

    graph.add_edge(START, "check_pending_confirmation")
    graph.add_conditional_edges(
        "check_pending_confirmation",
        route_after_check_pending_confirmation,
        {
            "create_complaint": "create_complaint",
            "select_tool": "select_tool",
        },
    )
    graph.add_edge("create_complaint", END)

    graph.add_conditional_edges(
        "select_tool",
        route_after_select_tool,
        {
            "call_tool": "call_tool",
            "no_tool_reply": "no_tool_reply",
        },
    )
    graph.add_edge("call_tool", "assess_risk")
    graph.add_conditional_edges(
        "assess_risk",
        route_after_assess_risk,
        {
            "confirm_complaint": "confirm_complaint",
            "end": END,
        },
    )
    graph.add_edge("confirm_complaint", END)
    graph.add_edge("no_tool_reply", END)
    return graph.compile()


# 3. 第一关：先判断用户是不是在确认上一轮的待处理动作。
def check_pending_confirmation_node(state: LangGraphAgentState) -> Dict[str, Any]:
    question = state["question"]
    user_id = state["user_id"]
    pending_confirmation = get_pending_confirmation(user_id)
    is_confirm_message = is_confirm_create_complaint_message(question)
    trace = {
        "framework": "langgraph",
        "nodes": ["check_pending_confirmation"],
        "user_id": user_id,
        "has_pending_confirmation": pending_confirmation is not None,
        "is_confirm_message": is_confirm_message,
    }
    return {
        "pending_confirmation": pending_confirmation,
        "is_confirm_message": is_confirm_message,
        "trace": trace,
    }


def route_after_check_pending_confirmation(state: LangGraphAgentState) -> str:
    if state.get("is_confirm_message") and state.get("pending_confirmation"):
        return "create_complaint"
    return "select_tool"


# 4. 确认后执行：用户第二轮确认后，真正创建投诉并返回投诉编号。
def create_complaint_node(state: LangGraphAgentState) -> Dict[str, Any]:
    pending = state["pending_confirmation"]
    result = create_complaint(
        user_id=state["user_id"],
        content=pending["content"],
        priority=pending.get("priority", "high"),
        handler=pending.get("handler"),
    )
    set_pending_confirmation(state["user_id"], None)

    complaint_id = result.get("complaint_id")
    trace = {
        **state["trace"],
        "nodes": state["trace"]["nodes"] + ["create_complaint"],
        "confirmed_action": "create_complaint",
        "complaint_id": complaint_id,
        "pending_cleared": True,
    }
    return {
        "reply": f"已为您创建投诉，投诉编号：{complaint_id}。客服主管会继续跟进处理。",
        "trace": trace,
        "tool_result": None,
        "created_complaint": result,
    }


# 5. 工具选择：不是确认消息时，先识别业务编号，再让 LLM/LangChain Agent 判断要不要查知识库。
def select_tool_node(state: LangGraphAgentState) -> Dict[str, Any]:
    selection = select_langgraph_tool(state["question"])
    trace = {
        **state["trace"],
        "nodes": state["trace"]["nodes"] + ["select_tool"],
        "tool_selected": selection["tool_name"],
        "tool_arguments": selection.get("arguments", {}),
        "agent_mode": selection["agent_mode"],
        "tool_selection_fallback_reason": selection.get("fallback_reason"),
    }
    return {"selection": selection, "trace": trace}


def route_after_select_tool(state: LangGraphAgentState) -> str:
    selection = state["selection"]
    if selection.get("tool_name") in {"search_knowledge", "handle_order_issue", "handle_logistics_issue"}:
        return "call_tool"
    return "no_tool_reply"


# 6. 工具调用：根据 tool_selected 调用订单、物流或知识库工具。
def call_tool_node(state: LangGraphAgentState) -> Dict[str, Any]:
    selection = state["selection"]
    tool_name = selection["tool_name"]

    if tool_name == "handle_order_issue":
        result = handle_order_issue(
            order_no=selection["arguments"]["order_no"],
            query=selection["arguments"]["query"],
        )
        reply = build_order_issue_reply(result)
        tool_result = result
        trace_extra = build_business_tool_trace(result)
    elif tool_name == "handle_logistics_issue":
        result = handle_logistics_issue(
            tracking_no=selection["arguments"]["tracking_no"],
            query=selection["arguments"]["query"],
        )
        reply = build_logistics_issue_reply(result)
        tool_result = result
        trace_extra = build_business_tool_trace(result)
    else:
        result = run_langchain_rag_agent(selection["arguments"]["query"])
        reply = result["reply"]
        tool_result = result["knowledge_result"]
        trace_extra = {
            "tool_result_found": result["knowledge_result"].get("found", False),
            "reply_source": result["trace"].get("reply_source"),
            "llm_used": result["trace"].get("llm_used", False),
            "fallback_reason": result["trace"].get("fallback_reason"),
        }

    trace = {
        **state["trace"],
        "nodes": state["trace"]["nodes"] + ["call_tool"],
        "tool_used": True,
        **trace_extra,
    }
    return {
        "reply": reply,
        "trace": trace,
        "tool_result": tool_result,
    }


# 7. 风险判断：判断这次问题是否需要“先确认，再建单”。
def assess_risk_node(state: LangGraphAgentState) -> Dict[str, Any]:
    risk_level = assess_risk_level(state["question"], state.get("tool_result"))
    trace = {
        **state["trace"],
        "nodes": state["trace"]["nodes"] + ["assess_risk"],
        "risk_level": risk_level,
    }
    return {"trace": trace}


def route_after_assess_risk(state: LangGraphAgentState) -> str:
    if state["trace"].get("risk_level") == "high":
        return "confirm_complaint"
    return "end"


# 8. 高风险确认：第一轮不直接写数据库，而是保存一个待确认动作。
def confirm_complaint_node(state: LangGraphAgentState) -> Dict[str, Any]:
    pending = {
        "type": PENDING_CONFIRMATION_TYPE,
        "action": "create_complaint",
        "content": build_pending_complaint_content(state),
        "priority": "high",
        "handler": "客服主管",
    }
    set_pending_confirmation(state["user_id"], pending)

    confirmation_text = (
        "\n\n我注意到这个问题可能属于高风险场景。"
        "如果您希望继续处理，可以回复“确认创建投诉”，我会为您进入投诉/升级处理流程。"
    )
    trace = {
        **state["trace"],
        "nodes": state["trace"]["nodes"] + ["confirm_complaint"],
        "requires_confirmation": True,
        "confirmation_action": "create_complaint",
        "pending_saved": True,
    }
    return {
        "reply": state["reply"] + confirmation_text,
        "trace": trace,
    }


# 9. 没选中工具：给出兜底回复，避免用户收到空结果。
def no_tool_reply_node(state: LangGraphAgentState) -> Dict[str, Any]:
    available_tools = [tool.name for tool in list_langchain_tools()]
    reason = "confirm_message_without_pending" if state.get("is_confirm_message") else "no_tool_selected"
    trace = {
        **state["trace"],
        "nodes": state["trace"]["nodes"] + ["no_tool_reply"],
        "tool_used": False,
        "available_tools": available_tools,
        "reason": reason,
        "risk_level": "normal",
    }
    return {
        "reply": "我暂时没有找到可以直接执行的待确认动作，可以先描述一下您遇到的问题。",
        "trace": trace,
        "tool_result": None,
    }


# 10. 辅助函数：下面这些函数不决定主流程，只帮助节点完成判断和存取。
def select_langgraph_tool(question: str) -> Dict[str, Any]:
    order_no = extract_order_no(question)
    if order_no:
        return {
            "tool_name": "handle_order_issue",
            "arguments": {"order_no": order_no, "query": question},
            "agent_mode": "langgraph_rule_selection",
            "fallback_reason": None,
        }

    tracking_no = extract_tracking_no(question)
    if tracking_no:
        return {
            "tool_name": "handle_logistics_issue",
            "arguments": {"tracking_no": tracking_no, "query": question},
            "agent_mode": "langgraph_rule_selection",
            "fallback_reason": None,
        }

    return select_tool_with_llm_fallback(question)


def assess_risk_level(question: str, tool_result: Optional[Dict[str, Any]] = None) -> str:
    if tool_result and tool_result.get("suggest_complaint"):
        return "high"

    normalized_question = question.lower().replace(" ", "")
    for keyword in HIGH_RISK_KEYWORDS:
        normalized_keyword = keyword.lower().replace(" ", "")
        if normalized_keyword in normalized_question:
            return "high"
    return "normal"


def is_confirm_create_complaint_message(question: str) -> bool:
    normalized_question = question.strip().replace(" ", "")
    return normalized_question in [message.replace(" ", "") for message in CONFIRM_CREATE_COMPLAINT_MESSAGES]


def get_pending_confirmation(user_id: str) -> Optional[Dict[str, Any]]:
    messages = SESSION_STORE.get(user_id)
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        if message.get("type") == PENDING_CONFIRMATION_RESOLVED_TYPE:
            return None
        if message.get("type") == PENDING_CONFIRMATION_TYPE and message.get("action") == "create_complaint":
            return message
    return None


def set_pending_confirmation(user_id: str, pending: Optional[Dict[str, Any]]) -> None:
    if pending is None:
        SESSION_STORE.append(
            user_id,
            {
                "type": PENDING_CONFIRMATION_RESOLVED_TYPE,
                "action": "create_complaint",
            },
        )
        return
    SESSION_STORE.append(user_id, pending)


def build_pending_complaint_content(state: LangGraphAgentState) -> str:
    tool_result = state.get("tool_result") or {}
    business_context = ""
    if tool_result.get("order_no"):
        business_context += f"\n订单号：{tool_result.get('order_no')}"
    if tool_result.get("tracking_no"):
        business_context += f"\n物流单号：{tool_result.get('tracking_no')}"
    if tool_result.get("agent_suggestion"):
        business_context += f"\n处理建议：{tool_result.get('agent_suggestion')}"

    return (
        f"用户问题：{state['question']}"
        f"{business_context}\n"
        f"Agent 已判断为高风险场景，需要升级处理。"
    )


def extract_order_no(question: str) -> Optional[str]:
    match = ORDER_NO_PATTERN.search(question)
    if match is None:
        return None
    return match.group(0).upper()


def extract_tracking_no(question: str) -> Optional[str]:
    match = TRACKING_NO_PATTERN.search(question)
    if match is None:
        return None
    return match.group(0).upper()


def build_order_issue_reply(result: Dict[str, Any]) -> str:
    if not result.get("found"):
        return f"没有查询到订单 {result.get('order_no')}，请先核对订单编号是否正确。"

    lines = [
        f"已查询到订单 {result.get('order_no')}，当前订单状态：{result.get('order_status')}。",
    ]
    if result.get("tracking_no"):
        lines.append(
            f"关联物流单号：{result.get('tracking_no')}，物流状态：{result.get('logistics_status')}。"
        )
    lines.append(result.get("agent_suggestion", "建议继续由客服核实处理。"))
    return "\n".join(lines)


def build_logistics_issue_reply(result: Dict[str, Any]) -> str:
    if not result.get("found"):
        return f"没有查询到物流单 {result.get('tracking_no')}，请先核对物流编号是否正确。"

    lines = [
        f"已查询到物流单 {result.get('tracking_no')}，当前物流状态：{result.get('logistics_status')}。",
    ]
    if result.get("order_no"):
        lines.append(f"关联订单号：{result.get('order_no')}。")
    lines.append(result.get("agent_suggestion", "建议继续由客服核实处理。"))
    return "\n".join(lines)


def build_business_tool_trace(result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "tool_result_found": result.get("found", False),
        "knowledge_found": result.get("knowledge_found", False),
        "suggest_complaint": result.get("suggest_complaint", False),
        "llm_used": False,
        "fallback_reason": None,
    }
