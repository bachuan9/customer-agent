import json
from typing import Any, Dict, List, Tuple

from app.services.llm_client import call_llm
from app.storage.db import insert_tool_call_log
from app.services.tool_registry import call_tool, get_tool_description, list_function_calling_tools


class LLMAgentError(RuntimeError):
    pass


def build_messages(user_message: str) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是电商客服系统里的工具选择助手。"
                "你只能根据用户问题选择一个合适的工具，不能自己编造订单、物流或投诉数据。"
                "如果用户问题同时涉及物流状态和平台政策，例如物流超时、48小时未更新、没发货，"
                "应优先选择 handle_logistics_issue。"
                "如果用户问题同时涉及订单状态和平台发货政策，例如订单超时、48小时未发货、还没发货，"
                "应优先选择 handle_order_issue。"
            ),
        },
        {
            "role": "user",
            "content": user_message,
        },
    ]


def extract_first_tool_call(llm_response: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    try:
        message = llm_response["choices"][0]["message"]
        tool_call = message["tool_calls"][0]
        function = tool_call["function"]
        tool_name = function["name"]
        raw_arguments = function.get("arguments") or "{}"
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMAgentError("LLM did not return a tool call") from exc

    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        raise LLMAgentError("LLM returned invalid tool arguments") from exc

    if not isinstance(arguments, dict):
        raise LLMAgentError("LLM tool arguments must be an object")

    return tool_name, arguments


def run_llm_tool_selection(message: str) -> Dict[str, Any]:
    messages = build_messages(message)
    tools = list_function_calling_tools()
    llm_response = call_llm(messages, tools)
    tool_name, arguments = extract_first_tool_call(llm_response)

    tool_description = get_tool_description(tool_name)
    if tool_description is not None and tool_description.get("mutates_data"):
        blocked_result = {
            "error": "confirmation_required",
            "tool": tool_name,
            "message": "Mutating tools require human confirmation",
        }
        insert_tool_call_log(
            tool_name,
            arguments,
            blocked_result,
            False,
            "confirmation_required",
            "llm_agent",
        )
        return {
            "tool_name": tool_name,
            "arguments": arguments,
            "tool_result": None,
            "requires_confirmation": True,
            "reason": "mutating_tool",
        }

    tool_result = call_tool(tool_name, arguments, source="llm_agent")

    return {
        "tool_name": tool_name,
        "arguments": arguments,
        "tool_result": tool_result,
        "requires_confirmation": False,
    }
