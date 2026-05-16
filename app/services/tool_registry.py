from typing import Any, Dict

from app.storage.db import insert_tool_call_log
from app.services.tools import (
    add_complaint_note,
    create_complaint,
    delete_complaint_note,
    get_complaint_detail,
    handle_logistics_issue,
    list_complaint_notes,
    list_complaints,
    query_logistics,
    query_order,
    search_knowledge,
    update_complaint,
    update_complaint_note,
    update_logistics,
    update_order,
)


PARAMETER_TYPES = {
    "order_no": "string",
    "tracking_no": "string",
    "complaint_id": "string",
    "note_id": "string",
    "user_id": "string",
    "content": "string",
    "author": "string",
    "status": "string",
    "priority": "string",
    "handler": "string",
    "query": "string",
}


# 1. 工具说明书：告诉 Agent 每个工具叫什么、需要什么参数、会不会修改数据。
TOOL_REGISTRY = [
    {
        "name": "query_order",
        "description": "查询订单状态",
        "parameters": {
            "order_no": "订单号，例如 A101",
        },
        "returns": {
            "found": "是否找到订单",
            "order_no": "订单号",
            "status": "订单状态",
        },
        "mutates_data": False,
    },
    {
        "name": "query_logistics",
        "description": "查询物流状态",
        "parameters": {
            "tracking_no": "物流单号，例如 L101",
        },
        "returns": {
            "found": "是否找到物流记录",
            "tracking_no": "物流单号",
            "status": "物流状态",
        },
        "mutates_data": False,
    },
    {
        "name": "handle_logistics_issue",
        "description": "处理物流异常问题，会同时查询物流状态和知识库政策，并判断是否建议创建投诉",
        "parameters": {
            "tracking_no": "物流单号，例如 L101",
            "query": "用户关于物流异常的完整问题",
        },
        "returns": {
            "found": "是否找到物流记录",
            "tracking_no": "物流单号",
            "order_no": "订单号",
            "logistics_status": "物流状态",
            "knowledge_found": "是否找到相关政策",
            "suggest_complaint": "是否建议创建投诉",
            "steps": "组合工具内部执行步骤",
        },
        "mutates_data": False,
    },
    {
        "name": "create_complaint",
        "description": "创建一条投诉记录",
        "parameters": {
            "user_id": "用户 ID",
            "content": "投诉内容",
        },
        "returns": {
            "complaint_id": "投诉编号",
            "status": "创建结果",
        },
        "mutates_data": True,
    },
    {
        "name": "list_complaints",
        "description": "查询投诉列表，可按用户过滤",
        "parameters": {
            "user_id": "可选，用户 ID",
            "status": "可选，投诉状态：pending、processing、resolved",
            "priority": "可选，投诉优先级：low、medium、high",
            "handler": "可选，处理人",
        },
        "returns": {
            "items": "投诉记录列表",
        },
        "mutates_data": False,
    },
    {
        "name": "get_complaint_detail",
        "description": "查询单条投诉详情和备注列表",
        "parameters": {
            "complaint_id": "投诉编号，例如 C-0001",
        },
        "returns": {
            "complaint": "投诉工单对象",
            "notes": "备注列表",
        },
        "mutates_data": False,
    },
    {
        "name": "search_knowledge",
        "description": "查询退货、售后、运费、退款等客服政策知识库",
        "parameters": {
            "query": "用户关于退货、售后、运费、退款、质保等政策的问题",
        },
        "returns": {
            "found": "是否找到相关知识",
            "query": "用户查询内容",
            "matches": "匹配到的知识库段落",
            "source": "知识来源文件",
        },
        "mutates_data": False,
    },
    {
        "name": "update_order",
        "description": "更新订单状态",
        "parameters": {
            "order_no": "订单号，例如 A101",
            "status": "订单状态：pending、shipped、delivered",
        },
        "returns": {
            "updated": "是否更新成功",
            "order": "更新后的订单对象，失败时为 None",
            "error": "失败原因，成功时为 None",
        },
        "mutates_data": True,
    },
    {
        "name": "update_logistics",
        "description": "更新物流状态",
        "parameters": {
            "tracking_no": "物流单号，例如 L101",
            "status": "物流状态：pending、in_transit、delivered",
        },
        "returns": {
            "updated": "是否更新成功",
            "logistics": "更新后的物流对象，失败时为 None",
            "error": "失败原因，成功时为 None",
        },
        "mutates_data": True,
    },
    {
        "name": "update_complaint",
        "description": "更新投诉状态、优先级或处理人",
        "parameters": {
            "complaint_id": "投诉编号，例如 C-0001",
            "status": "可选，投诉状态：pending、processing、resolved",
            "priority": "可选，投诉优先级：low、medium、high",
            "handler": "可选，处理人",
        },
        "returns": {
            "complaint": "更新后的投诉对象",
        },
        "mutates_data": True,
    },
    {
        "name": "add_complaint_note",
        "description": "给投诉工单添加客服备注",
        "parameters": {
            "complaint_id": "投诉编号，例如 C-0001",
            "content": "备注内容",
            "author": "可选，备注作者",
        },
        "returns": {
            "note": "新增后的备注对象",
        },
        "mutates_data": True,
    },
    {
        "name": "list_complaint_notes",
        "description": "查询某个投诉工单的客服备注列表",
        "parameters": {
            "complaint_id": "投诉编号，例如 C-0001",
        },
        "returns": {
            "items": "备注记录列表",
        },
        "mutates_data": False,
    },
    {
        "name": "delete_complaint_note",
        "description": "删除一条投诉备注",
        "parameters": {
            "note_id": "备注编号，例如 N-0001",
        },
        "returns": {
            "deleted": "是否删除成功",
            "note_id": "备注编号",
        },
        "mutates_data": True,
    },
    {
        "name": "update_complaint_note",
        "description": "修改一条投诉备注内容",
        "parameters": {
            "note_id": "备注编号，例如 N-0001",
            "content": "新的备注内容",
        },
        "returns": {
            "note": "修改后的备注对象",
        },
        "mutates_data": True,
    },
]

# 2. 工具函数映射：把工具名连接到真正执行的 Python 函数。
TOOL_FUNCTIONS = {
    "query_order": query_order,
    "query_logistics": query_logistics,
    "handle_logistics_issue": handle_logistics_issue,
    "create_complaint": create_complaint,
    "list_complaints": list_complaints,
    "get_complaint_detail": get_complaint_detail,
    "search_knowledge": search_knowledge,
    "update_order": update_order,
    "update_logistics": update_logistics,
    "update_complaint": update_complaint,
    "add_complaint_note": add_complaint_note,
    "list_complaint_notes": list_complaint_notes,
    "delete_complaint_note": delete_complaint_note,
    "update_complaint_note": update_complaint_note,
}


# 3. 工具说明查询：给外部查看或内部校验工具描述用。
def list_tool_descriptions():
    return TOOL_REGISTRY


def get_required_parameters(tool_description: Dict[str, Any]):
    required = []
    for parameter_name, parameter_description in tool_description["parameters"].items():
        if not parameter_description.startswith("可选"):
            required.append(parameter_name)
    return required


def to_function_calling_tool(tool_description: Dict[str, Any]):
    properties = {}
    for parameter_name, parameter_description in tool_description["parameters"].items():
        properties[parameter_name] = {
            "type": PARAMETER_TYPES.get(parameter_name, "string"),
            "description": parameter_description,
        }

    return {
        "type": "function",
        "function": {
            "name": tool_description["name"],
            "description": tool_description["description"],
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": get_required_parameters(tool_description),
            },
        },
    }


def list_function_calling_tools():
    return [to_function_calling_tool(tool) for tool in TOOL_REGISTRY]


def get_tool_description(name: str):
    for tool in TOOL_REGISTRY:
        if tool["name"] == name:
            return tool
    return None


# 4. 参数检查：调用工具前检查必填参数是否缺失。
def get_missing_arguments(tool_description: Dict[str, Any], arguments: Dict[str, Any]):
    missing = []
    for parameter_name, parameter_description in tool_description["parameters"].items():
        if parameter_description.startswith("可选"):
            continue
        if parameter_name not in arguments:
            missing.append(parameter_name)
    return missing


# 5. 工具调用入口：根据工具名找到函数，并把参数传进去执行。
def call_tool(name: str, arguments: Dict[str, Any], source: str = "rule_agent"):
    tool = TOOL_FUNCTIONS.get(name)
    if tool is None:
        result = {"error": "tool_not_found", "tool": name}
        insert_tool_call_log(name, arguments, result, False, "tool_not_found", source)
        return result
    
    tool_description = get_tool_description(name)
    missing_arguments = get_missing_arguments(tool_description, arguments)
    if missing_arguments:
        result = {
            "error": "missing_argument",
            "tool": name,
            "arguments": missing_arguments,
        }
        insert_tool_call_log(name, arguments, result, False, "missing_argument", source)
        return result

    try:
        result = tool(**arguments)
    except Exception as exc:
        error_result = {"error": "tool_exception", "tool": name, "message": str(exc)}
        insert_tool_call_log(name, arguments, error_result, False, str(exc), source)
        raise

    success = not (isinstance(result, dict) and result.get("error"))
    error = result.get("error") if isinstance(result, dict) else None
    insert_tool_call_log(name, arguments, result, success, error, source)
    return result


# 6. 工具错误格式化：把工具层错误转换成用户能看懂的回复。
def format_tool_error(result: Dict[str, Any]) -> str:
    if result.get("error") == "tool_not_found":
        return f"暂不支持工具：{result.get('tool')}"

    if result.get("error") == "missing_argument":
        prompts = {
            "order_no": "请提供订单号，例如 A101。",
            "tracking_no": "请提供物流单号，例如 L101。",
            "complaint_id": "请提供投诉编号，例如 C-0001。",
            "status": "请提供要更新的状态。",
            "user_id": "请提供用户 ID。",
            "content": "请提供投诉内容。",
        }
        missing = result.get("arguments", [])
        if missing:
            return prompts.get(missing[0], f"请补充参数：{missing[0]}")
        return "请补充缺失参数。"

    return "工具调用失败，请检查参数后重试。"
