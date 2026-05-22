import json
from typing import Any, Dict, Optional

from app.services.langchain_rag_agent import run_langchain_rag_agent
from app.services.langchain_tools import list_langchain_tools
from app.services.llm_client import LLMClientError, call_llm


# langchain_agent.py 阅读地图：
# 1. run_langchain_agent(...) 是 LangChain Agent 实验入口。
# 2. select_tool_with_llm_fallback(...) 先让 LLM 选工具，失败就用关键词规则兜底。
# 3. search_knowledge 命中后交给 LangChain RAG 链路生成回复。
# 4. build_tool_reply(...) / build_no_tool_reply(...) 统一返回 reply + trace。


POLICY_KEYWORDS = [
    "退款",
    "退货",
    "物流",
    "发货",
    "48小时",
    "48 小时",
    "会员",
    "积分",
    "优惠券",
    "生鲜",
    "破损",
    "政策",
]


class LangChainAgentSelectionError(RuntimeError):
    pass


# 1. LangChain Agent 入口：选择工具，然后决定是否进入 RAG 链路。
def run_langchain_agent(question: str) -> Dict[str, Any]:
    selection = select_tool_with_llm_fallback(question)
    tool_name = selection["tool_name"]

    if tool_name == "search_knowledge":
        tool_query = selection["arguments"]["query"]
        result = run_langchain_rag_agent(tool_query)
        return build_tool_reply(question, result, selection)

    return build_no_tool_reply(question, selection)


# 2. 工具选择：优先 LLM，失败后用确定性关键词规则。
def select_tool_with_llm_fallback(question: str) -> Dict[str, Any]:
    try:
        selection = select_langchain_tool_with_llm(question)
        selection["agent_mode"] = "llm_tool_selection"
        selection["fallback_reason"] = None
        return selection
    except (LLMClientError, LangChainAgentSelectionError) as exc:
        tool_name = select_langchain_tool(question)
        return {
            "tool_name": tool_name,
            "arguments": {"query": question} if tool_name else {},
            "agent_mode": "deterministic_tool_selection",
            "fallback_reason": str(exc),
        }


# 3. LLM 工具选择细节：构造提示词、解析 JSON、校验工具名。
def select_langchain_tool_with_llm(question: str) -> Dict[str, Any]:
    messages = build_tool_selection_messages(question)
    llm_response = call_llm(messages)
    return parse_tool_selection_response(llm_response, question)


def build_tool_selection_messages(question: str) -> list[dict[str, str]]:
    tools_text = "\n".join(
        f"- {tool.name}: {tool.description}" for tool in list_langchain_tools()
    )
    return [
        {
            "role": "system",
            "content": (
                "你是电商客服 Agent 的工具选择器。"
                "你只负责判断是否需要调用工具，不负责回答用户。"
                "如果需要工具，只能从可用工具列表里选择。"
                "请只返回 JSON，不要返回多余解释。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"用户问题：{question}\n\n"
                f"可用工具：\n{tools_text}\n\n"
                "返回格式："
                '{"tool_name":"search_knowledge","arguments":{"query":"用户问题"}}'
                "；如果不需要工具，返回："
                '{"tool_name":null,"arguments":{}}'
            ),
        },
    ]


def parse_tool_selection_response(llm_response: Dict[str, Any], question: str) -> Dict[str, Any]:
    try:
        content = llm_response["choices"][0]["message"]["content"]
        payload = json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise LangChainAgentSelectionError("LLM did not return valid tool selection JSON") from exc

    tool_name = payload.get("tool_name")
    arguments = payload.get("arguments") or {}
    available_tool_names = {tool.name for tool in list_langchain_tools()}

    if tool_name is None:
        return {"tool_name": None, "arguments": {}}

    if tool_name not in available_tool_names:
        raise LangChainAgentSelectionError(f"LLM selected unknown tool: {tool_name}")

    if tool_name == "search_knowledge":
        query = arguments.get("query") or question
        return {"tool_name": tool_name, "arguments": {"query": query}}

    raise LangChainAgentSelectionError(f"Unsupported tool selected: {tool_name}")


# 4. 规则兜底工具选择：政策类关键词命中时选择 search_knowledge。
def select_langchain_tool(question: str) -> Optional[str]:
    normalized_question = question.lower().replace(" ", "")
    for keyword in POLICY_KEYWORDS:
        normalized_keyword = keyword.lower().replace(" ", "")
        if normalized_keyword in normalized_question:
            return "search_knowledge"
    return None


# 5. 响应包装：把工具结果整理成前端能展示的 reply + trace。
def build_tool_reply(question: str, result: Dict[str, Any], selection: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "question": question,
        "reply": result["reply"],
        "trace": {
            "framework": "langchain",
            "agent_mode": selection["agent_mode"],
            "tool_selected": selection["tool_name"],
            "tool_arguments": selection["arguments"],
            "tool_used": True,
            "tool_result_found": result["knowledge_result"].get("found", False),
            "reply_source": result["trace"].get("reply_source"),
            "llm_used": result["trace"].get("llm_used", False),
            "fallback_reason": result["trace"].get("fallback_reason"),
            "tool_selection_fallback_reason": selection.get("fallback_reason"),
        },
        "tool_result": result["knowledge_result"],
    }


def build_no_tool_reply(question: str, selection: Dict[str, Any]) -> Dict[str, Any]:
    available_tools = [tool.name for tool in list_langchain_tools()]
    return {
        "question": question,
        "reply": "我暂时没有选择到合适的 LangChain 工具处理这个问题，可以转到普通客服 Agent 继续处理。",
        "trace": {
            "framework": "langchain",
            "agent_mode": selection["agent_mode"],
            "tool_selected": None,
            "tool_arguments": selection.get("arguments", {}),
            "tool_used": False,
            "available_tools": available_tools,
            "reason": "no_tool_selected",
            "tool_selection_fallback_reason": selection.get("fallback_reason"),
        },
        "tool_result": None,
    }
