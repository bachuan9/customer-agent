import re
from app.core.config import settings
from app.models.schemas import ChatRequest
from app.storage.database_session import DatabaseSessionStore
from app.storage.db import insert_tool_call_log
from app.services.llm_agent import LLMAgentError, run_llm_tool_selection
from app.services.llm_client import LLMClientError
from app.services.llm_reply import LLMReplyError, generate_llm_reply, generate_rag_llm_reply
from app.services.tool_registry import call_tool, format_tool_error
from app.services.langgraph_agent import get_pending_confirmation, run_langgraph_agent, set_pending_confirmation


# Agent 主流程阅读地图：
# 1. /chat 接口调用 run_agent_with_steps(req)，这是客服窗口的真实入口。
# 2. run_agent_with_steps(req) 调用 run_agent_trace(req)，拿到 reply 和 trace。
# 3. run_agent_trace(req) 读取 message、user_id、role，并用 detect_intent(message) 判断意图。
# 4. 如果是确认类消息，优先处理 pending action，避免重复创建或误更新。
# 5. 如果是订单/物流异常，优先调用组合工具 handle_order_issue / handle_logistics_issue。
# 6. 对订单/物流高风险场景，主 Agent 会接入 LangGraph 工作流，获得节点流水线和决策解释。
# 7. 如果开启 LLM，再尝试 run_llm_tool_selection(message)，失败时降级到规则 Agent。
# 8. 规则 Agent 通过 handle_intent(...) 分发到查询、更新、投诉、备注等业务分支。
# 9. call_tool(...) 通过 tool_registry 调用 tools.py 里的具体工具函数。
# 10. format_xxx_reply(...) 和 build_agent_steps(...) 分别生成用户回复和前端步骤面板。
# 11. 最终返回 reply + steps + trace 给 routes.py，再返回给 web/app.js。



# 简单的会话记忆（按 user_id 保存上下文，基于 SQLite 持久化）
MEMORY = DatabaseSessionStore()


# 1. 显示文案：把程序内部状态转换成用户能看懂的中文。
ORDER_STATUS_LABELS = {
    "pending": "待处理",
    "shipped": "已发货",
    "delivered": "已送达",
}


LOGISTICS_STATUS_LABELS = {
    "pending": "待处理",
    "in_transit": "运输中",
    "delivered": "已送达",
}


COMPLAINT_STATUS_LABELS = {
    "pending": "待处理",
    "processing": "处理中",
    "resolved": "已解决",
}


COMPLAINT_PRIORITY_LABELS = {
    "low": "低",
    "medium": "中",
    "high": "高",
}


COMPLAINT_PRIORITY_KEYWORDS = {
    "高优先级": "high",
    "中优先级": "medium",
    "低优先级": "low",
}


COMPLAINT_STATUS_KEYWORDS = {
    "待处理": "pending",
    "处理中": "processing",
    "已解决": "resolved",
}


KNOWLEDGE_KEYWORDS = {
    "政策",
    "规则",
    "知识库",
    "物流政策",
    "物流规则",
    "物流超时",
    "超时政策",
    "超时规则",
    "发货政策",
    "发货规则",
    "配送政策",
    "配送规则",
    "会员政策",
    "会员规则",
    "积分规则",
    "优惠券规则",
    "退货",
    "售后",
    "运费",
    "退款",
    "到账",
    "质量问题",
    "质保",
    "维修",
    "换货",
    "无理由",
}


LOGISTICS_ISSUE_KEYWORDS = {
    "48小时",
    "48 小时",
    "没发货",
    "未发货",
    "没更新",
    "未更新",
    "延迟",
    "超时",
    "怎么还",
}


ORDER_ISSUE_KEYWORDS = {
    "48小时",
    "48 小时",
    "没发货",
    "未发货",
    "一直没发货",
    "延迟",
    "超时",
    "怎么还",
}


ESCALATION_SUGGESTION_KEYWORDS = {
    "48小时",
    "48 小时",
    "超时",
    "没发货",
    "未发货",
    "没更新",
    "未更新",
    "延迟",
}


ROLE_LABELS = {
    "agent": "普通客服",
    "manager": "主管",
}


TOOL_ROLE_PERMISSIONS = {
    "create_complaint": {"agent", "manager"},
    "add_complaint_note": {"agent", "manager"},
    "update_complaint_note": {"agent", "manager"},
    "update_order": {"manager"},
    "update_logistics": {"manager"},
    "update_complaint": {"manager"},
    "delete_complaint_note": {"manager"},
}


# 2. 基础查询回复：把订单/物流查询结果组织成回复文字。
def format_order_status_reply(order_no, status):
    label = ORDER_STATUS_LABELS.get(status, status)
    return f"您的订单 {order_no} 当前状态是：{label}。"


def format_logistics_status_reply(tracking_no, status):
    label = LOGISTICS_STATUS_LABELS.get(status, status)
    return f"您的物流 {tracking_no} 当前状态是：{label}。"


def check_order(order_id, user_id=None):
    result = call_tool("query_order", {"order_no": order_id})
    if result.get("error"):
        return format_tool_error(result)
    if not result["found"]:
        return "未找到"
    if user_id:
        set_recent_context(user_id, order_no=order_id)
    return format_order_status_reply(order_id, result["status"])



def check_logistics(tracking_no, user_id=None):
    result = call_tool("query_logistics", {"tracking_no": tracking_no})
    if result.get("error"):
        return format_tool_error(result)
    if not result["found"]:
        return "未找到"
    if user_id:
        set_recent_context(user_id, tracking_no=tracking_no, order_no=result.get("order_no"))
    return format_logistics_status_reply(tracking_no, result["status"])



# 3. 信息提取和上下文记忆：从用户输入里提取编号、状态、优先级，并保存多轮上下文。
def extract_id(message, prefix):
    # 从一句话里提取以 prefix 开头的编号（如 A001 或 L002）
    # 兼容无空格和中文标点写法
    match = re.search(rf"{re.escape(prefix)}\d+", message)
    return match.group(0) if match else None


def extract_complaint_id(message):
    match = re.search(r"C-\d{4}", message, re.IGNORECASE)
    return match.group(0).upper() if match else None


def extract_note_id(message):
    match = re.search(r"N-\d{4}", message, re.IGNORECASE)
    return match.group(0).upper() if match else None


def extract_handler_filter(message):
    match = re.search(r"查看\s*(.+?)\s*的投诉", message)
    return match.group(1).strip() if match else None


def extract_status(message, allowed_statuses):
    for status in allowed_statuses:
        if status in message:
            return status
    return None


def extract_priority(message):
    return extract_status(message.lower(), {"low", "medium", "high"})


def is_logistics_issue(message):
    return bool(extract_id(message, "L")) and any(keyword in message for keyword in LOGISTICS_ISSUE_KEYWORDS)


def is_order_issue(message):
    return bool(extract_id(message, "A")) and any(keyword in message for keyword in ORDER_ISSUE_KEYWORDS)


def should_suggest_complaint(message):
    return any(keyword in message for keyword in ESCALATION_SUGGESTION_KEYWORDS)


PENDING_COMPLAINT_CONTINUE_INTENTS = {"create_complaint"}


CONTEXT_LOGISTICS_FOLLOW_UP_KEYWORDS = {
    "那物流呢",
    "物流呢",
    "查下物流",
    "查一下物流",
    "它的物流",
    "这个订单的物流",
}


CONTEXT_ORDER_FOLLOW_UP_KEYWORDS = {
    "那订单呢",
    "订单呢",
    "查下订单",
    "查一下订单",
    "它的订单",
    "这个物流的订单",
}


def get_recent_context(user_id):
    for item in reversed(MEMORY.get(user_id)):
        if isinstance(item, dict) and item.get("type") == "recent_context":
            return item
    return {}


def set_recent_context(user_id, **context):
    recent = get_recent_context(user_id)
    recent.update({key: value for key, value in context.items() if value})
    recent["type"] = "recent_context"
    MEMORY.append(user_id, recent)


def is_context_logistics_follow_up(message):
    return any(keyword in message for keyword in CONTEXT_LOGISTICS_FOLLOW_UP_KEYWORDS)


def is_context_order_follow_up(message):
    return any(keyword in message for keyword in CONTEXT_ORDER_FOLLOW_UP_KEYWORDS)


def remember_tool_result_context(user_id, tool_name, result):
    if not isinstance(result, dict):
        return

    if tool_name == "query_order" and result.get("found"):
        set_recent_context(user_id, order_no=result.get("order_no"))
        return

    if tool_name == "query_logistics" and result.get("found"):
        set_recent_context(user_id, tracking_no=result.get("tracking_no"), order_no=result.get("order_no"))
        return

    if tool_name == "query_logistics_by_order" and result.get("found"):
        set_recent_context(user_id, order_no=result.get("order_no"), tracking_no=result.get("tracking_no"))
        return

    if tool_name in {"handle_order_issue", "handle_logistics_issue"} and result.get("found"):
        set_recent_context(user_id, order_no=result.get("order_no"), tracking_no=result.get("tracking_no"))


# 4. 意图识别：判断用户这句话想做什么。
def detect_intent(message):
    # 先判断更具体的意图，避免“更新订单”被误判成普通“查订单”
    if message.strip() == "确认执行":
        return "confirm_llm_action"
    if "确认更新订单" in message:
        return "confirm_update_order"
    if "确认更新物流" in message:
        return "confirm_update_logistics"
    if "确认创建投诉" in message:
        return "confirm_create_complaint"
    if "取消创建投诉" in message:
        return "cancel_create_complaint"
    if "查看备注" in message:
        return "list_complaint_notes"
    if "查看投诉" in message and extract_complaint_id(message):
        return "get_complaint_detail"
    if "查看" in message and "投诉" in message:
        return "list_complaints"
    if "修改备注" in message:
        return "update_complaint_note"
    if "删除备注" in message:
        return "delete_complaint_note"
    if "备注投诉" in message:
        return "add_complaint_note"
    if "设置投诉" in message:
        return "update_complaint_priority"
    if "更新投诉" in message:
        return "update_complaint_status"
    if "主管接单" in message:
        return "manager_take_complaint"
    if "分配投诉" in message:
        return "assign_complaint_handler"
    if "解决投诉" in message:
        return "resolve_complaint"
    if is_order_issue(message):
        return "order_issue"
    if is_logistics_issue(message):
        return "logistics_issue"
    if any(keyword in message for keyword in KNOWLEDGE_KEYWORDS):
        return "search_knowledge"
    if "投诉" in message:
        return "create_complaint"
    if "更新订单" in message:
        return "update_order"
    if "更新物流" in message:
        return "update_logistics"
    if "订单" in message:
        return "query_order"
    if "物流" in message:
        return "query_logistics"
    return "unknown"


# 5. 回复格式化：把工具结果、更新结果、列表结果、备注结果整理成用户能读的话。
def format_order_update_reply(result):
    if result["updated"]:
        order = result["order"]
        label = ORDER_STATUS_LABELS.get(order["status"], order["status"])
        return f"订单 {order['order_no']} 已为您更新为：{label}。"
    if result["error"] == "invalid_status":
        return "订单状态不合法，请使用 pending、shipped 或 delivered"
    if result["error"] == "order_not_found":
        return "未找到订单，无法更新"
    return "订单更新失败"


def format_logistics_update_reply(result):
    if result["updated"]:
        logistics = result["logistics"]
        label = LOGISTICS_STATUS_LABELS.get(logistics["status"], logistics["status"])
        return f"物流 {logistics['tracking_no']} 已为您更新为：{label}。"
    if result["error"] == "invalid_status":
        return "物流状态不合法，请使用 pending、in_transit 或 delivered"
    if result["error"] == "logistics_not_found":
        return "未找到物流记录，无法更新"
    return "物流更新失败"


def format_complaint_update_reply(result):
    if result is None:
        return "未找到投诉工单，无法更新"
    if result.get("error"):
        return format_tool_error(result)

    complaint = result
    status_label = COMPLAINT_STATUS_LABELS.get(complaint["status"], complaint["status"])
    priority_label = COMPLAINT_PRIORITY_LABELS.get(complaint["priority"], complaint["priority"])
    handler = complaint.get("handler") or "暂未分配"
    return f"投诉 {complaint['id']} 已更新：状态 {status_label}，优先级 {priority_label}，处理人 {handler}。"


def build_rag_trace(knowledge_result):
    if not knowledge_result:
        return {"found": False, "query": "", "sources": [], "top_score": None, "match_reason": "未执行知识库检索"}

    matches = knowledge_result.get("matches") or []
    top_match = matches[0] if matches else {}
    return {
        "found": knowledge_result.get("found", False),
        "query": knowledge_result.get("query", ""),
        "sources": knowledge_result.get("sources", []),
        "top_score": top_match.get("score"),
        "retrieval_mode": top_match.get("retrieval_mode"),
        "keyword_score": top_match.get("keyword_score"),
        "embedding_score": top_match.get("embedding_score"),
        "top_title": top_match.get("title"),
        "top_source_type": top_match.get("source_type"),
        "match_reason": top_match.get("match_reason", "未命中可靠知识"),
    }


def format_complaint_notes_reply(complaint_id, notes):
    if notes is None:
        return "未找到投诉工单，无法查看备注"
    if not notes:
        return f"投诉 {complaint_id} 暂无备注。"

    lines = [f"投诉 {complaint_id} 的备注："]
    for note in notes:
        lines.append(f"- {note['id']} | {note['created_at']} | {note['author']}：{note['content']}")
    return "\n".join(lines)


def format_complaint_detail_reply(result):
    if result is None:
        return "未找到投诉工单。"

    complaint = result["complaint"]
    notes = result["notes"]
    handler = complaint.get("handler") or "暂未分配"
    lines = [
        f"投诉详情 {complaint['id']}：",
        f"用户：{complaint['user_id']}",
        f"状态：{complaint['status']}",
        f"优先级：{complaint['priority']}",
        f"跟进状态：{complaint.get('follow_up_status') or '正常'}",
        f"跟进原因：{complaint.get('follow_up_reason') or '暂无'}",
        f"处理人：{handler}",
        f"内容：{complaint['content']}",
        f"创建时间：{complaint['created_at']}",
        f"更新时间：{complaint.get('updated_at') or '暂无'}",
        f"解决时间：{complaint.get('resolved_at') or '暂无'}",
        "备注：",
    ]
    if not notes:
        lines.append("- 暂无备注")
    else:
        for note in notes:
            lines.append(f"- {note['id']} | {note['created_at']} | {note['author']}：{note['content']}")
    return "\n".join(lines)


# 5.1 LLM 和组合工具回复：把工具结果转成用户能看懂的中文。
def format_knowledge_no_answer_reply():
    return (
        "暂未在知识库中找到可靠的相关政策。"
        "为避免误导用户，建议转人工客服或由主管确认后再答复。"
    )


def format_llm_tool_selection_reply(selection):
    tool_name = selection["tool_name"]
    arguments = selection["arguments"]
    result = selection["tool_result"]

    if selection.get("requires_confirmation"):
        return (
            "这个操作会修改系统数据，需要人工确认后才能执行。\n"
            f"模型建议调用工具：{tool_name}\n"
            f"建议参数：{arguments}\n"
            "如果确认无误，请回复：确认执行。"
        )

    if isinstance(result, dict) and result.get("error"):
        return format_tool_error(result)

    if tool_name == "query_order":
        if not result["found"]:
            return "未找到"
        return format_order_status_reply(result["order_no"], result["status"])

    if tool_name == "query_logistics":
        if not result["found"]:
            return "未找到"
        return format_logistics_status_reply(result["tracking_no"], result["status"])

    if tool_name == "handle_logistics_issue":
        return format_logistics_issue_reply(
            result["tracking_no"],
            result["logistics_result"],
            result["knowledge_result"],
            agent_suggestion=result.get("agent_suggestion"),
            suggest_complaint=result.get("suggest_complaint", False),
        )

    if tool_name == "handle_order_issue":
        return format_order_issue_reply(
            result["order_no"],
            result["order_result"],
            result.get("logistics_result", {}),
            result["knowledge_result"],
            agent_suggestion=result.get("agent_suggestion"),
            suggest_complaint=result.get("suggest_complaint", False),
        )

    if tool_name == "update_order":
        return format_order_update_reply(result)

    if tool_name == "update_logistics":
        return format_logistics_update_reply(result)

    if tool_name == "list_complaints":
        return format_complaint_list_reply(result, arguments)

    if tool_name == "get_complaint_detail":
        return format_complaint_detail_reply(result)

    if tool_name == "search_knowledge":
        if not result.get("found"):
            return format_knowledge_no_answer_reply()
        lines = ["我查到以下相关政策："]
        for match in result.get("matches", []):
            if isinstance(match, dict):
                lines.append(f"- {match['content']}")
                if match.get("match_reason"):
                    lines.append(f"  命中依据：{match['match_reason']}")
            else:
                lines.append(f"- {match}")
        sources = result.get("sources") or ([result["source"]] if result.get("source") else [])
        if sources:
            lines.append(f"参考来源：{', '.join(sources)}")
        return "\n".join(lines)

    if tool_name == "update_complaint":
        return format_complaint_update_reply(result)

    if tool_name == "add_complaint_note":
        if result is None:
            return "未找到投诉工单，无法添加备注"
        complaint_id = arguments.get("complaint_id", result.get("complaint_id", ""))
        return f"已给投诉 {complaint_id} 添加备注，备注编号 {result['id']}：{result['content']}"

    if tool_name == "list_complaint_notes":
        return format_complaint_notes_reply(arguments.get("complaint_id"), result)

    if tool_name == "update_complaint_note":
        if result is None:
            return "未找到备注，无法修改"
        note_id = arguments.get("note_id", result["id"])
        return f"已修改备注 {note_id}：{result['content']}"

    if tool_name == "delete_complaint_note":
        if result.get("deleted"):
            return f"已删除备注 {result['note_id']}。"
        return "未找到备注，无法删除"

    if tool_name == "create_complaint":
        return f"已收到投诉，编号 {result['complaint_id']}"

    return "工具已执行完成。"


def format_logistics_issue_reply(
    tracking_no,
    logistics_result,
    knowledge_result,
    agent_suggestion=None,
    suggest_complaint=False,
):
    lines = ["已同时查询物流状态和平台政策。"]

    if logistics_result.get("error"):
        lines.append(format_tool_error(logistics_result))
    elif logistics_result.get("found"):
        label = LOGISTICS_STATUS_LABELS.get(logistics_result["status"], logistics_result["status"])
        lines.append(f"我帮您查了一下，物流 {tracking_no} 当前状态是：{label}。")
    else:
        lines.append(f"我暂时没有查到物流 {tracking_no} 的记录，建议先核对物流单号是否正确。")

    append_issue_knowledge_reply(
        lines,
        knowledge_result,
        heading="结合平台物流异常处理规则，可以这样处理：",
        suggestion="建议您先安抚用户，并联系仓库或承运商核实发货/更新情况；如果确认超时，可继续为用户创建投诉或升级处理。",
        fallback="暂未在知识库中找到对应的物流异常规则，建议先联系仓库或承运商进一步核实。",
    )
    if agent_suggestion:
        lines.append(f"客服处理建议：{agent_suggestion}")
    if suggest_complaint:
        lines.append("如果用户希望继续处理，可以回复“确认创建投诉”，为用户创建投诉并升级给客服主管跟进。")

    return "\n".join(lines)


def format_order_issue_reply(
    order_no,
    order_result,
    logistics_result=None,
    knowledge_result=None,
    agent_suggestion=None,
    suggest_complaint=False,
):
    lines = ["已同时查询订单状态和平台发货政策。"]
    logistics_result = logistics_result or {}
    knowledge_result = knowledge_result or {}

    if order_result.get("error"):
        lines.append(format_tool_error(order_result))
    elif order_result.get("found"):
        label = ORDER_STATUS_LABELS.get(order_result["status"], order_result["status"])
        lines.append(f"我帮您查了一下，订单 {order_no} 当前状态是：{label}。")
    else:
        lines.append(f"我暂时没有查到订单 {order_no} 的记录，建议先核对订单号是否正确。")

    if logistics_result.get("error"):
        lines.append(format_tool_error(logistics_result))
    elif logistics_result.get("found"):
        label = LOGISTICS_STATUS_LABELS.get(logistics_result["status"], logistics_result["status"])
        lines.append(f"该订单关联物流 {logistics_result['tracking_no']} 当前状态是：{label}。")
    else:
        lines.append("暂未查到该订单关联的物流记录，建议继续核实是否已生成物流单。")

    append_issue_knowledge_reply(
        lines,
        knowledge_result,
        heading="结合平台发货时效规则，可以这样处理：",
        suggestion="建议您先安抚用户，并核实订单是否属于预售、定制、大促或仓库延迟场景；如果确认超时，可继续为用户创建投诉或升级处理。",
        fallback="暂未在知识库中找到对应的发货规则，建议先联系仓库进一步核实。",
    )
    if agent_suggestion:
        lines.append(f"客服处理建议：{agent_suggestion}")
    if suggest_complaint:
        lines.append("如果用户希望继续处理，可以回复“确认创建投诉”，为用户创建投诉并升级给客服主管跟进。")

    return "\n".join(lines)


def append_issue_knowledge_reply(lines, knowledge_result, *, heading, suggestion, fallback):
    if knowledge_result.get("error"):
        lines.append(format_tool_error(knowledge_result))
        return

    if not knowledge_result.get("found"):
        lines.append(fallback)
        return

    lines.append(heading)
    for match in knowledge_result.get("matches", []):
        content = match["content"] if isinstance(match, dict) else match
        lines.append(f"- {content}")
        if isinstance(match, dict) and match.get("match_reason"):
            lines.append(f"  命中依据：{match['match_reason']}")

    lines.append(suggestion)
    sources = knowledge_result.get("sources") or ([knowledge_result["source"]] if knowledge_result.get("source") else [])
    if sources:
        lines.append(f"参考来源：{', '.join(sources)}")


def extract_note_content(message, complaint_id):
    content = message.replace("备注投诉", "", 1).replace(complaint_id, "", 1).strip()
    return content.strip("：: ")


def extract_note_author_and_content(message, complaint_id):
    content = extract_note_content(message, complaint_id)
    match = re.match(r"([^:：\s]+)\s*[:：]\s*(.+)$", content)
    if not match:
        return "客服", content
    return match.group(1).strip(), match.group(2).strip()


def extract_update_note_content(message, note_id):
    content = message.replace("修改备注", "", 1).replace(note_id, "", 1).strip()
    return content.strip("：: ")


def build_update_confirmation(kind, item_id, status):
    if kind == "order":
        label = ORDER_STATUS_LABELS.get(status, status)
        return f"您确认要把订单 {item_id} 更新为“{label}”吗？请回复：确认更新订单 {item_id} {status}"

    label = LOGISTICS_STATUS_LABELS.get(status, status)
    return f"您确认要把物流 {item_id} 更新为“{label}”吗？请回复：确认更新物流 {item_id} {status}"


# 6. 投诉创建和筛选辅助函数：处理投诉原因、投诉列表、筛选条件。
def extract_reason(message):
    # 提取投诉原因，只有明确包含"原因:xxx"或"原因：xxx"时才认为有原因
    match = re.search(r"原因\s*[:：]\s*(.+)$", message)
    if match:
        return match.group(1).strip()
    return ""  # 没有明确原因时返回空字符串，让系统继续问


def clean_reason(reason, order_id):
    # 去掉订单号和常见前缀，避免原因里混入编号
    cleaned = reason
    if order_id:
        cleaned = cleaned.replace(order_id, "")
    cleaned = re.sub(r"订单号\s*[:：]?", "", cleaned)
    cleaned = re.sub(r"订单\s*[:：]?", "", cleaned)
    cleaned = re.sub(r"原因\s*[:：]?", "", cleaned)
    return cleaned.strip(" ：:-")


def create_complaint(user_id, content, priority="medium", handler=None):
    # 保存到数据库并返回投诉编号
    result = call_tool(
        "create_complaint",
        {"user_id": user_id, "content": content, "priority": priority, "handler": handler},
    )
    if result.get("error"):
        return format_tool_error(result)
    return result["complaint_id"]


def list_complaints(user_id=None, status=None, priority=None, handler=None, follow_up_status=None):
    # 查询历史投诉，user_id 为空时返回全部
    return list_complaints_with_filters(
        user_id=user_id,
        status=status,
        priority=priority,
        handler=handler,
        follow_up_status=follow_up_status,
    )


def list_complaints_with_filters(user_id=None, status=None, priority=None, handler=None, follow_up_status=None):
    arguments = {}
    if user_id is not None:
        arguments["user_id"] = user_id
    if status is not None:
        arguments["status"] = status
    if priority is not None:
        arguments["priority"] = priority
    if handler is not None:
        arguments["handler"] = handler
    if follow_up_status is not None:
        arguments["follow_up_status"] = follow_up_status
    return call_tool("list_complaints", arguments)


def format_complaint_list_reply(items, filters=None):
    filters = filters or {}
    if not items:
        return "没有找到符合条件的投诉。"

    filter_text_parts = []
    if filters.get("status"):
        filter_text_parts.append(f"状态={filters['status']}")
    if filters.get("priority"):
        filter_text_parts.append(f"优先级={filters['priority']}")
    if filters.get("handler"):
        filter_text_parts.append(f"处理人={filters['handler']}")
    if filters.get("follow_up_status"):
        filter_text_parts.append(f"跟进状态={filters['follow_up_status']}")
    title = "投诉列表"
    if filter_text_parts:
        title += "（" + "，".join(filter_text_parts) + "）"

    lines = [title + "："]
    for item in items[:10]:
        handler = item.get("handler") or "暂未分配"
        lines.append(
            f"- {item['id']} | 状态 {item['status']} | 优先级 {item['priority']} | 处理人 {handler} | {item['content']}"
        )
    if len(items) > 10:
        lines.append(f"还有 {len(items) - 10} 条未显示。")
    return "\n".join(lines)


def extract_complaint_filters(message):
    status = None
    priority = None

    for keyword, value in COMPLAINT_STATUS_KEYWORDS.items():
        if keyword in message:
            status = value
            break

    for keyword, value in COMPLAINT_PRIORITY_KEYWORDS.items():
        if keyword in message:
            priority = value
            break

    handler = extract_handler_filter(message)
    return {"status": status, "priority": priority, "handler": handler}


# 7. Pending 状态和权限辅助函数：保存多轮投诉流程、待确认更新、待确认 LLM 动作。
def get_pending_complaint(user_id):
    # 从记忆里读取该用户是否有未完成的投诉
    data = MEMORY.get(user_id)
    print(f"[DEBUG] get_pending_complaint: user_id={user_id}, all_data={data}")
    for item in reversed(data):
        if isinstance(item, dict) and item.get("type") == "pending_complaint":
            print(f"[DEBUG] Found pending_complaint={item}")
            return item
    print("[DEBUG] No pending_complaint found")
    return None


def set_pending_complaint(user_id, pending):
    # 保存未完成的投诉（先清空旧的，再存新的，避免重复）
    MEMORY.clear(user_id)
    MEMORY.append(user_id, pending)


def get_pending_update(user_id):
    # 从记忆里读取该用户是否有待确认的更新动作
    data = MEMORY.get(user_id)
    for item in reversed(data):
        if isinstance(item, dict) and item.get("type") == "pending_update":
            return item
    return None


def set_pending_update(user_id, pending):
    # 保存待确认更新。这里先清空旧状态，避免一个用户同时挂着多个待确认动作。
    MEMORY.clear(user_id)
    MEMORY.append(user_id, pending)


def get_pending_llm_action(user_id):
    data = MEMORY.get(user_id)
    for item in reversed(data):
        if isinstance(item, dict) and item.get("type") == "pending_llm_action":
            return item
    return None


def set_pending_llm_action(user_id, action):
    MEMORY.clear(user_id)
    MEMORY.append(user_id, action)


def can_role_execute_tool(role, tool_name):
    allowed_roles = TOOL_ROLE_PERMISSIONS.get(tool_name, {"manager"})
    return role in allowed_roles


def format_permission_denied_reply(role, tool_name):
    role_label = ROLE_LABELS.get(role, role)
    return f"当前角色“{role_label}”没有权限执行 {tool_name}，请切换为主管角色后再确认。"


# 8. 二次确认流程：处理订单/物流更新、LLM 写操作、创建投诉确认。
def handle_confirm_update(message, user_id, pending_update):
    if not pending_update:
        return "当前没有待确认的更新操作，请先发起更新。"

    if pending_update["kind"] == "order":
        item_id = extract_id(message, "A")
        status = extract_status(message, {"pending", "shipped", "delivered"})
        if item_id != pending_update["item_id"] or status != pending_update["status"]:
            return build_update_confirmation("order", pending_update["item_id"], pending_update["status"])

        result = call_tool("update_order", {"order_no": item_id, "status": status})
        MEMORY.clear(user_id)
        return format_order_update_reply(result)

    item_id = extract_id(message, "L")
    status = extract_status(message, {"pending", "in_transit", "delivered"})
    if item_id != pending_update["item_id"] or status != pending_update["status"]:
        return build_update_confirmation("logistics", pending_update["item_id"], pending_update["status"])

    result = call_tool("update_logistics", {"tracking_no": item_id, "status": status})
    MEMORY.clear(user_id)
    return format_logistics_update_reply(result)


def handle_confirm_llm_action(user_id, role="agent"):
    pending_action = get_pending_llm_action(user_id)
    if not pending_action:
        return "当前没有等待确认的 LLM 操作。"

    tool_name = pending_action["tool_name"]
    arguments = pending_action["arguments"]
    if not can_role_execute_tool(role, tool_name):
        insert_tool_call_log(
            tool_name,
            arguments,
            {
                "error": "permission_denied",
                "tool": tool_name,
                "role": role,
                "user_id": user_id,
            },
            False,
            "permission_denied",
            "rbac_denied",
        )
        return format_permission_denied_reply(role, tool_name)

    try:
        result = call_tool(tool_name, arguments, source="llm_confirmed_action")
    except ValueError as exc:
        MEMORY.clear(user_id)
        return f"确认执行失败：{exc}"

    MEMORY.clear(user_id)
    selection = {
        "tool_name": tool_name,
        "arguments": arguments,
        "tool_result": result,
        "requires_confirmation": False,
    }
    return format_llm_tool_selection_reply(selection)


def build_issue_complaint_content(pending):
    issue_type = pending.get("issue_type")
    order_id = pending.get("order_id")
    tracking_no = pending.get("tracking_no")
    reason = pending.get("reason") or "用户反馈订单/物流异常"

    parts = []
    if order_id:
        parts.append(f"订单号:{order_id}")
    if tracking_no:
        parts.append(f"物流号:{tracking_no}")
    if issue_type:
        parts.append(f"类型:{issue_type}")
    parts.append(f"原因:{reason}")
    return " ".join(parts)


def handle_confirm_create_complaint(user_id, pending_existing):
    if not pending_existing or pending_existing.get("type") != "pending_complaint":
        return "当前没有待确认创建的投诉，请先描述订单或物流异常。"

    content = build_issue_complaint_content(pending_existing)
    priority = pending_existing.get("priority", "medium")
    handler = pending_existing.get("handler")
    complaint_id = create_complaint(user_id, content, priority=priority, handler=handler)
    MEMORY.clear(user_id)
    reply = f"已为用户创建投诉，编号 {complaint_id}。"
    reply += f"\n优先级：{priority}。"
    reply += f"\n处理人：{handler or '暂未分配'}。"
    return reply


def handle_cancel_create_complaint(user_id, pending_existing):
    langgraph_pending = get_pending_confirmation(user_id)
    if langgraph_pending:
        set_pending_confirmation(user_id, None)
        return "已取消创建投诉。"

    if not pending_existing or pending_existing.get("type") != "pending_complaint":
        return "当前没有待取消的投诉创建流程。"

    MEMORY.clear(user_id)
    return "已取消创建投诉。"


def build_agent_steps(
    intent,
    pending_existing=None,
    pending_after=None,
    selection=None,
    execution_mode="rule_agent",
    llm_reply_generated=False,
    llm_fallback_error=None,
    reply_source="rule_template",
    langgraph_trace=None,
    langgraph_decision_summary=None,
):
    steps = [f"识别意图：{intent}"]

    if execution_mode == "llm_agent":
        steps.append("执行模式：LLM Agent（本次调用了 LLM）")
    elif execution_mode == "langgraph_agent":
        steps.append("执行模式：LangGraph Agent（主客服窗口接入状态机工作流）")
    elif llm_fallback_error:
        steps.append("执行模式：规则 Agent（LLM 调用失败后自动降级）")
        steps.append(f"LLM 降级原因：{llm_fallback_error}")
    elif execution_mode == "rule_agent":
        steps.append("执行模式：规则 Agent（本次未调用 LLM）")

    if reply_source == "llm_reply":
        steps.append("回复来源：LLM 润色生成")
    elif reply_source == "rag_llm_reply":
        steps.append("回复来源：RAG 命中后由 LLM 生成")
    elif reply_source == "langgraph_workflow":
        steps.append("回复来源：LangGraph 工作流")
    elif reply_source == "llm_template_fallback":
        steps.append("回复来源：LLM 工具结果模板")
    else:
        steps.append("回复来源：规则模板")

    if intent == "confirm_create_complaint":
        if langgraph_trace:
            nodes = " -> ".join(langgraph_trace.get("nodes", []))
            steps.append("接入 LangGraph 工作流")
            if nodes:
                steps.append(f"LangGraph 节点：{nodes}")
        if pending_existing:
            steps.append(f"读取会话记忆：{pending_existing.get('status', pending_existing.get('type'))}")
        else:
            steps.append("读取会话记忆：无待确认投诉")
        steps.extend(["整理投诉内容", "调用工具：create_complaint", "清空待确认动作"])
        return steps

    if intent == "cancel_create_complaint":
        if pending_existing:
            steps.append(f"读取会话记忆：{pending_existing.get('status', pending_existing.get('type'))}")
        else:
            steps.append("读取会话记忆：无待取消投诉")
        steps.append("清空待确认动作")
        return steps

    tool_steps = {
        "order_issue": [
            "调用组合工具：handle_order_issue",
            "内部调用：query_order",
            "内部调用：query_logistics_by_order",
            "内部调用：search_knowledge",
            "生成客服处理建议",
        ],
        "logistics_issue": [
            "调用组合工具：handle_logistics_issue",
            "内部调用：query_logistics",
            "内部调用：search_knowledge",
            "生成客服处理建议",
        ],
        "query_order": ["调用工具：query_order"],
        "query_logistics": ["调用工具：query_logistics"],
        "search_knowledge": ["调用工具：search_knowledge"],
        "create_complaint": ["调用工具：create_complaint"],
        "manager_take_complaint": ["调用工具：update_complaint", "设置处理人：客服主管", "设置状态：processing"],
        "confirm_llm_action": ["读取待确认 LLM 动作"],
        "confirm_update_order": ["读取待确认订单更新", "调用工具：update_order"],
        "confirm_update_logistics": ["读取待确认物流更新", "调用工具：update_logistics"],
    }
    steps.extend(tool_steps.get(intent, []))

    if selection:
        steps.append(f"LLM 选择工具：{selection['tool_name']}")
        if llm_reply_generated:
            steps.append("LLM 生成最终回复")
        if selection.get("requires_confirmation"):
            steps.append("保存待确认动作：pending_llm_action")

    if intent in {"order_issue", "logistics_issue"}:
        if langgraph_trace:
            nodes = " -> ".join(langgraph_trace.get("nodes", []))
            steps.append("接入 LangGraph 工作流")
            if nodes:
                steps.append(f"LangGraph 节点：{nodes}")
        if langgraph_decision_summary:
            selected_tool = langgraph_decision_summary.get("selected_tool")
            reason = langgraph_decision_summary.get("why_this_tool")
            if selected_tool:
                steps.append(f"LangGraph 决策工具：{selected_tool}")
            if reason:
                steps.append(f"LangGraph 决策解释：{reason}")
        steps.append("判断是否需要建议创建投诉")
        if pending_after and pending_after.get("status") == "waiting_confirm":
            steps.append("保存待确认动作：waiting_confirm")
    if pending_existing:
        steps.append(f"读取会话记忆：{pending_existing.get('status', pending_existing.get('type'))}")

    return steps


# 9. 规则 Agent 主分发：根据识别出的 intent 进入对应处理分支。
def handle_intent(message, user_id, intent, pending_existing):
    if intent == "confirm_llm_action":
        return handle_confirm_llm_action(user_id)

    if intent == "confirm_create_complaint":
        return handle_confirm_create_complaint(user_id, pending_existing)

    if intent == "cancel_create_complaint":
        return handle_cancel_create_complaint(user_id, pending_existing)

    if intent in {"confirm_update_order", "confirm_update_logistics"}:
        pending_update = get_pending_update(user_id)
        return handle_confirm_update(message, user_id, pending_update)

    if intent == "list_complaints":
        filters = extract_complaint_filters(message)
        result = list_complaints_with_filters(**filters)
        return format_complaint_list_reply(result, filters)

    if intent == "get_complaint_detail":
        complaint_id = extract_complaint_id(message)
        result = call_tool("get_complaint_detail", {"complaint_id": complaint_id})
        return format_complaint_detail_reply(result)

    if intent == "order_issue":
        order_no = extract_id(message, "A")
        result = call_tool("handle_order_issue", {"order_no": order_no, "query": message})
        if result.get("suggest_complaint"):
            set_pending_complaint(
                user_id,
                {
                    "type": "pending_complaint",
                    "status": "waiting_confirm",
                    "issue_type": "订单异常",
                    "order_id": order_no,
                    "reason": message,
                    "priority": "high",
                    "handler": "客服主管",
                },
            )
        return format_order_issue_reply(
            order_no,
            result["order_result"],
            result.get("logistics_result", {}),
            result["knowledge_result"],
            agent_suggestion=result.get("agent_suggestion"),
            suggest_complaint=result.get("suggest_complaint", False),
        )

    if intent == "logistics_issue":
        tracking_no = extract_id(message, "L")
        result = call_tool("handle_logistics_issue", {"tracking_no": tracking_no, "query": message})
        if result.get("suggest_complaint"):
            set_pending_complaint(
                user_id,
                {
                    "type": "pending_complaint",
                    "status": "waiting_confirm",
                    "issue_type": "物流异常",
                    "order_id": result.get("order_no"),
                    "tracking_no": tracking_no,
                    "reason": message,
                    "priority": "high",
                    "handler": "客服主管",
                },
            )
        return format_logistics_issue_reply(
            tracking_no,
            result["logistics_result"],
            result["knowledge_result"],
            agent_suggestion=result.get("agent_suggestion"),
            suggest_complaint=result.get("suggest_complaint", False),
        )

    if intent == "search_knowledge":
        result = call_tool("search_knowledge", {"query": message})
        selection = {
            "tool_name": "search_knowledge",
            "arguments": {"query": message},
            "tool_result": result,
            "requires_confirmation": False,
        }
        return format_llm_tool_selection_reply(selection)

    if intent == "add_complaint_note":
        complaint_id = extract_complaint_id(message)
        if not complaint_id:
            return "没有识别到投诉编号，请写成：备注投诉 C-0001 已联系用户"
        author, content = extract_note_author_and_content(message, complaint_id)
        if not content:
            return "没有识别到备注内容，请写成：备注投诉 C-0001 Alice: 已联系用户"
        try:
            result = call_tool(
                "add_complaint_note",
                {"complaint_id": complaint_id, "content": content, "author": author},
            )
        except ValueError as exc:
            return f"备注添加失败：{exc}"
        if result is None:
            return "未找到投诉工单，无法添加备注"
        return f"已给投诉 {complaint_id} 添加备注，备注编号 {result['id']}：{result['content']}"

    if intent == "list_complaint_notes":
        complaint_id = extract_complaint_id(message)
        if not complaint_id:
            return "没有识别到投诉编号，请写成：查看备注 C-0001"
        result = call_tool("list_complaint_notes", {"complaint_id": complaint_id})
        return format_complaint_notes_reply(complaint_id, result)

    if intent == "update_complaint_note":
        note_id = extract_note_id(message)
        if not note_id:
            return "没有识别到备注编号，请写成：修改备注 N-0001 新的备注内容"
        content = extract_update_note_content(message, note_id)
        if not content:
            return "没有识别到新的备注内容，请写成：修改备注 N-0001 已重新联系用户"
        try:
            result = call_tool("update_complaint_note", {"note_id": note_id, "content": content})
        except ValueError as exc:
            return f"备注修改失败：{exc}"
        if result is None:
            return "未找到备注，无法修改"
        return f"已修改备注 {note_id}：{result['content']}"

    if intent == "delete_complaint_note":
        note_id = extract_note_id(message)
        if not note_id:
            return "没有识别到备注编号，请写成：删除备注 N-0001"
        result = call_tool("delete_complaint_note", {"note_id": note_id})
        if result.get("deleted"):
            return f"已删除备注 {note_id}。"
        return "未找到备注，无法删除"

    if intent == "update_complaint_priority":
        complaint_id = extract_complaint_id(message)
        priority = extract_priority(message)
        if not complaint_id:
            return "没有识别到投诉编号，请写成：设置投诉 C-0001 high"
        if not priority:
            return "没有识别到投诉优先级，请使用 low、medium 或 high"
        try:
            result = call_tool("update_complaint", {"complaint_id": complaint_id, "priority": priority})
        except ValueError as exc:
            return f"投诉优先级更新失败：{exc}"
        return format_complaint_update_reply(result)

    if intent == "update_complaint_status":
        complaint_id = extract_complaint_id(message)
        status = extract_status(message, {"pending", "processing", "resolved"})
        if not complaint_id:
            return "没有识别到投诉编号，请写成：更新投诉 C-0001 processing"
        if not status:
            return "没有识别到投诉状态，请使用 pending、processing 或 resolved"
        try:
            result = call_tool("update_complaint", {"complaint_id": complaint_id, "status": status})
        except ValueError as exc:
            return f"投诉更新失败：{exc}"
        return format_complaint_update_reply(result)

    if intent == "assign_complaint_handler":
        complaint_id = extract_complaint_id(message)
        if not complaint_id:
            return "没有识别到投诉编号，请写成：分配投诉 C-0001 Alice"
        handler = message.replace("分配投诉", "").replace(complaint_id, "").strip()
        if not handler:
            return "没有识别到处理人，请写成：分配投诉 C-0001 Alice"
        try:
            result = call_tool("update_complaint", {"complaint_id": complaint_id, "handler": handler})
        except ValueError as exc:
            return f"投诉分配失败：{exc}"
        return format_complaint_update_reply(result)

    if intent == "manager_take_complaint":
        complaint_id = extract_complaint_id(message)
        if not complaint_id:
            return "没有识别到投诉编号，请写成：主管接单 C-0001"
        try:
            result = call_tool(
                "update_complaint",
                {"complaint_id": complaint_id, "status": "processing", "handler": "客服主管"},
            )
        except ValueError as exc:
            return f"主管接单失败：{exc}"
        return format_complaint_update_reply(result)

    if intent == "resolve_complaint":
        complaint_id = extract_complaint_id(message)
        if not complaint_id:
            return "没有识别到投诉编号，请写成：解决投诉 C-0001"
        try:
            result = call_tool("update_complaint", {"complaint_id": complaint_id, "status": "resolved"})
        except ValueError as exc:
            return f"投诉解决失败：{exc}"
        return format_complaint_update_reply(result)

    if (
        pending_existing
        and pending_existing.get("status") == "waiting_confirm"
        and intent in PENDING_COMPLAINT_CONTINUE_INTENTS
    ):
        return "已准备好投诉内容。如需创建投诉，请回复：确认创建投诉。"

    if intent == "create_complaint" or (
        pending_existing and intent in PENDING_COMPLAINT_CONTINUE_INTENTS
    ):
        order_id = extract_id(message, "A")
        pending = pending_existing or {"type": "pending_complaint"}

        # 尝试补全订单号
        if order_id:
            pending["order_id"] = order_id

        # 根据流程状态，智能提取原因
        # 如果已经问过原因（status="waiting_reason"），任何输入都直接作为原因
        if pending.get("status") == "waiting_reason":
            reason = message.strip()  # 直接使用用户输入
        else:
            reason = extract_reason(message)
            if reason:  # 只有提取到内容才调用 clean_reason
                reason = clean_reason(reason, pending.get("order_id"))
            else:
                reason = None
        
        if reason:
            pending["reason"] = reason

        # 如果缺订单号，就先问订单号
        if not pending.get("order_id"):
            pending["status"] = "waiting_order"
            set_pending_complaint(user_id, pending)
            return "请提供订单号（例如：A001）"

        # 如果缺原因，就先问原因
        if not pending.get("reason"):
            pending["status"] = "waiting_reason"
            set_pending_complaint(user_id, pending)
            return "请简要描述投诉原因"

        # 信息齐全，创建投诉
        content = f"订单号:{pending['order_id']} 原因:{pending['reason']}"
        print(f"[DEBUG] Creating complaint - pending={pending}, content={content}")
        complaint_id = create_complaint(
            user_id,
            content,
            priority=pending.get("priority", "medium"),
            handler=pending.get("handler"),
        )
        MEMORY.clear(user_id)
        return f"已收到投诉，编号 {complaint_id}"

    if intent == "update_order":
        order_id = extract_id(message, "A")
        status = extract_status(message, {"pending", "shipped", "delivered"})
        if not order_id:
            return "没有识别到订单号，请写成：更新订单 A101 shipped"
        if not status:
            return "没有识别到订单状态，请使用 pending、shipped 或 delivered"
        set_pending_update(
            user_id,
            {
                "type": "pending_update",
                "kind": "order",
                "item_id": order_id,
                "status": status,
            },
        )
        return build_update_confirmation("order", order_id, status)

    if intent == "update_logistics":
        tracking_no = extract_id(message, "L")
        status = extract_status(message, {"pending", "in_transit", "delivered"})
        if not tracking_no:
            return "没有识别到物流号，请写成：更新物流 L101 delivered"
        if not status:
            return "没有识别到物流状态，请使用 pending、in_transit 或 delivered"
        set_pending_update(
            user_id,
            {
                "type": "pending_update",
                "kind": "logistics",
                "item_id": tracking_no,
                "status": status,
            },
        )
        return build_update_confirmation("logistics", tracking_no, status)

    # 如果包含“订单”，就查订单
    if intent == "query_order":
        # 订单号默认以 A 开头
        order_id = extract_id(message, "A")
        if order_id:
            return check_order(order_id, user_id)
        if is_context_order_follow_up(message):
            recent = get_recent_context(user_id)
            recent_order_no = recent.get("order_no")
            if recent_order_no:
                return check_order(recent_order_no, user_id)
        return "没有识别到订单号，请写在句子里，比如：查订单 A001"

    # 如果包含“物流”，就查物流
    if intent == "query_logistics":
        # 物流单号默认以 L 开头
        tracking_no = extract_id(message, "L")
        if tracking_no:
            return check_logistics(tracking_no, user_id)
        if is_context_logistics_follow_up(message):
            recent = get_recent_context(user_id)
            recent_tracking_no = recent.get("tracking_no")
            if recent_tracking_no:
                return check_logistics(recent_tracking_no, user_id)
            recent_order_no = recent.get("order_no")
            if recent_order_no:
                result = call_tool("query_logistics_by_order", {"order_no": recent_order_no})
                if result.get("error"):
                    return format_tool_error(result)
                if not result["found"]:
                    return f"暂时没有查到订单 {recent_order_no} 的关联物流。"
                set_recent_context(user_id, order_no=recent_order_no, tracking_no=result.get("tracking_no"))
                return format_logistics_status_reply(result["tracking_no"], result["status"])
        return "没有识别到物流号，请写在句子里，比如：查物流 L002"

    # 其他情况给提示
    return "我只能查询订单或物流，请再说一次。"


# 10. 主 Agent 执行链路：先处理高优先级分支，再尝试 LLM，最后规则兜底。
def run_agent_trace(req):
    # 取出用户输入的一句话
    message = req.message
    user_id = req.user_id
    role = req.role
    intent = detect_intent(message)
    trace = {
        "intent": intent,
        "execution_mode": "rule_agent",
        "selection": None,
        "llm_reply_generated": False,
        "llm_fallback_error": None,
        "reply_source": "rule_template",
        "rag": None,
    }

    if intent == "confirm_llm_action":
        trace["reply"] = handle_confirm_llm_action(user_id, role)
        return trace

    if intent == "confirm_create_complaint":
        pending_existing = get_pending_complaint(user_id)
        langgraph_result = run_langgraph_agent(message, user_id=user_id)
        if langgraph_result.get("created_complaint"):
            trace["execution_mode"] = "langgraph_agent"
            trace["reply_source"] = "langgraph_workflow"
            trace["langgraph"] = langgraph_result.get("trace")
            trace["decision_summary"] = langgraph_result.get("decision_summary")
            trace["reply"] = langgraph_result["reply"]
            return trace
        trace["reply"] = handle_confirm_create_complaint(user_id, pending_existing)
        return trace

    if intent == "cancel_create_complaint":
        pending_existing = get_pending_complaint(user_id)
        trace["reply"] = handle_cancel_create_complaint(user_id, pending_existing)
        return trace

    if intent == "order_issue":
        order_no = extract_id(message, "A")
        langgraph_result = run_langgraph_agent(message, user_id=user_id)
        result = langgraph_result.get("tool_result") or {}
        set_recent_context(user_id, order_no=order_no, tracking_no=result.get("tracking_no"))
        trace["rag"] = build_rag_trace(result.get("knowledge_result"))
        trace["execution_mode"] = "langgraph_agent"
        trace["reply_source"] = "langgraph_workflow"
        trace["langgraph"] = langgraph_result.get("trace")
        trace["decision_summary"] = langgraph_result.get("decision_summary")
        trace["reply"] = langgraph_result["reply"]
        return trace

    if intent == "logistics_issue":
        tracking_no = extract_id(message, "L")
        langgraph_result = run_langgraph_agent(message, user_id=user_id)
        result = langgraph_result.get("tool_result") or {}
        set_recent_context(user_id, tracking_no=tracking_no, order_no=result.get("order_no"))
        trace["rag"] = build_rag_trace(result.get("knowledge_result"))
        trace["execution_mode"] = "langgraph_agent"
        trace["reply_source"] = "langgraph_workflow"
        trace["langgraph"] = langgraph_result.get("trace")
        trace["decision_summary"] = langgraph_result.get("decision_summary")
        trace["reply"] = langgraph_result["reply"]
        return trace

    # 如果开启 LLM，就先让大模型选择工具；失败时退回下面的规则 Agent。
    if settings.llm_enabled:
        try:
            selection = run_llm_tool_selection(message)
            trace["execution_mode"] = "llm_agent"
            trace["selection"] = selection
            remember_tool_result_context(user_id, selection.get("tool_name"), selection.get("tool_result"))
            if selection.get("tool_name") == "search_knowledge":
                trace["rag"] = build_rag_trace(selection.get("tool_result"))
            print(f"[DEBUG] LLM selected tool: {selection['tool_name']} {selection['arguments']}")
            if selection.get("requires_confirmation"):
                print("[DEBUG] LLM selected mutating tool; confirmation required")
                set_pending_llm_action(
                    user_id,
                    {
                        "type": "pending_llm_action",
                        "tool_name": selection["tool_name"],
                        "arguments": selection["arguments"],
                    },
                )
                trace["reply"] = format_llm_tool_selection_reply(selection)
                trace["reply_source"] = "llm_template_fallback"
                return trace
            try:
                reply = generate_llm_reply(message, selection)
                trace["llm_reply_generated"] = True
                trace["reply_source"] = "llm_reply"
                print("[DEBUG] LLM generated final reply")
                trace["reply"] = reply
                return trace
            except (LLMClientError, LLMReplyError) as exc:
                print(f"[DEBUG] LLM reply fallback to template: {exc}")
                trace["llm_fallback_error"] = str(exc)
            trace["reply"] = format_llm_tool_selection_reply(selection)
            trace["reply_source"] = "llm_template_fallback"
            return trace
        except (LLMClientError, LLMAgentError, ValueError) as exc:
            print(f"[DEBUG] LLM fallback to rule agent: {exc}")
            trace["execution_mode"] = "rule_agent"
            trace["selection"] = None
            trace["llm_fallback_error"] = str(exc)

    # 用户明确发起投诉时，重置该用户的未完成状态
    if intent == "create_complaint":
        MEMORY.clear(user_id)

    # DEBUG: 打印接收到的消息
    print(f"[DEBUG] user_id={user_id}, message={message}")

    # 如果之前有未完成投诉，即使这次没说“投诉”，也要继续投诉流程
    pending_existing = get_pending_complaint(user_id)
    print(f"[DEBUG] pending_existing={pending_existing}")

    trace["reply"] = handle_intent(message, user_id, intent, pending_existing)
    if intent == "search_knowledge":
        result = call_tool("search_knowledge", {"query": message})
        trace["rag"] = build_rag_trace(result)
        if settings.llm_enabled and result.get("found"):
            try:
                trace["reply"] = generate_rag_llm_reply(message, result)
                trace["llm_reply_generated"] = True
                trace["reply_source"] = "rag_llm_reply"
                return trace
            except (LLMClientError, LLMReplyError) as exc:
                trace["llm_fallback_error"] = str(exc)
        trace["reply"] = format_llm_tool_selection_reply(
            {
                "tool_name": "search_knowledge",
                "arguments": {"query": message},
                "tool_result": result,
                "requires_confirmation": False,
            }
        )
    return trace


# 11. Agent 对外入口：每一次 /chat 请求都会从这里开始。
def run_agent(req):
    return run_agent_trace(req)["reply"]


def run_agent_with_steps(req):
    message = req.message
    user_id = req.user_id
    intent = detect_intent(message)
    pending_before = get_pending_complaint(user_id)

    trace = run_agent_trace(req)
    reply = trace["reply"]
    pending_after = get_pending_complaint(user_id)
    steps = build_agent_steps(
        trace["intent"],
        pending_existing=pending_before,
        pending_after=pending_after,
        selection=trace.get("selection"),
        execution_mode=trace.get("execution_mode", "rule_agent"),
        llm_reply_generated=trace.get("llm_reply_generated", False),
        llm_fallback_error=trace.get("llm_fallback_error"),
        reply_source=trace.get("reply_source", "rule_template"),
        langgraph_trace=trace.get("langgraph"),
        langgraph_decision_summary=trace.get("decision_summary"),
    )
    return {"reply": reply, "steps": steps, "trace": trace}
