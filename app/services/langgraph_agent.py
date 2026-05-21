from typing import Any, Dict, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.services.langchain_agent import select_tool_with_llm_fallback
from app.services.langchain_rag_agent import run_langchain_rag_agent
from app.services.langchain_tools import list_langchain_tools


class LangGraphAgentState(TypedDict, total=False):
    question: str
    selection: Dict[str, Any]
    reply: str
    trace: Dict[str, Any]
    tool_result: Optional[Dict[str, Any]]


def run_langgraph_agent(question: str) -> Dict[str, Any]:
    workflow = build_langgraph_workflow()
    final_state = workflow.invoke({"question": question})
    return {
        "question": final_state["question"],
        "reply": final_state["reply"],
        "trace": final_state["trace"],
        "tool_result": final_state.get("tool_result"),
    }


def build_langgraph_workflow():
    graph = StateGraph(LangGraphAgentState)
    graph.add_node("select_tool", select_tool_node)
    graph.add_node("call_tool", call_tool_node)
    graph.add_node("no_tool_reply", no_tool_reply_node)

    graph.add_edge(START, "select_tool")
    graph.add_conditional_edges(
        "select_tool",
        route_after_select_tool,
        {
            "call_tool": "call_tool",
            "no_tool_reply": "no_tool_reply",
        },
    )
    graph.add_edge("call_tool", END)
    graph.add_edge("no_tool_reply", END)
    return graph.compile()


def select_tool_node(state: LangGraphAgentState) -> Dict[str, Any]:
    selection = select_tool_with_llm_fallback(state["question"])
    trace = {
        "framework": "langgraph",
        "nodes": ["select_tool"],
        "tool_selected": selection["tool_name"],
        "tool_arguments": selection.get("arguments", {}),
        "agent_mode": selection["agent_mode"],
        "tool_selection_fallback_reason": selection.get("fallback_reason"),
    }
    return {"selection": selection, "trace": trace}


def route_after_select_tool(state: LangGraphAgentState) -> str:
    selection = state["selection"]
    if selection.get("tool_name") == "search_knowledge":
        return "call_tool"
    return "no_tool_reply"


def call_tool_node(state: LangGraphAgentState) -> Dict[str, Any]:
    selection = state["selection"]
    tool_query = selection["arguments"]["query"]
    result = run_langchain_rag_agent(tool_query)
    trace = {
        **state["trace"],
        "nodes": state["trace"]["nodes"] + ["call_tool"],
        "tool_used": True,
        "tool_result_found": result["knowledge_result"].get("found", False),
        "reply_source": result["trace"].get("reply_source"),
        "llm_used": result["trace"].get("llm_used", False),
        "fallback_reason": result["trace"].get("fallback_reason"),
    }
    return {
        "reply": result["reply"],
        "trace": trace,
        "tool_result": result["knowledge_result"],
    }


def no_tool_reply_node(state: LangGraphAgentState) -> Dict[str, Any]:
    available_tools = [tool.name for tool in list_langchain_tools()]
    trace = {
        **state["trace"],
        "nodes": state["trace"]["nodes"] + ["no_tool_reply"],
        "tool_used": False,
        "available_tools": available_tools,
        "reason": "no_tool_selected",
    }
    return {
        "reply": "我暂时没有选择到合适的 LangGraph 工具处理这个问题，可以转到普通客服 Agent 继续处理。",
        "trace": trace,
        "tool_result": None,
    }
