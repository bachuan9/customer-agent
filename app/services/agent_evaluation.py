from typing import Any, Dict

from app.core.config import settings
from app.models.schemas import ChatRequest
from app.services.agent import run_agent_with_steps


AGENT_EVAL_CASES = [
    {
        "name": "\u5355\u8f6e\u8ba2\u5355\u67e5\u8be2",
        "messages": ["\u67e5\u8ba2\u5355 A101"],
        "expected_intent": "query_order",
        "expected_execution_mode": "rule_agent",
        "expected_reply_keywords": ["\u8ba2\u5355 A101"],
    },
    {
        "name": "\u591a\u8f6e\u4e0a\u4e0b\u6587\u8865\u5168\u7269\u6d41",
        "messages": ["\u67e5\u8ba2\u5355 A101", "\u90a3\u7269\u6d41\u5462"],
        "expected_intent": "query_logistics",
        "expected_execution_mode": "rule_agent",
        "expected_reply_keywords": ["\u7269\u6d41 L101"],
    },
    {
        "name": "RAG \u7269\u6d41\u653f\u7b56\u68c0\u7d22",
        "messages": ["\u7269\u6d41\u8d85\u65f6\u653f\u7b56"],
        "expected_intent": "search_knowledge",
        "expected_execution_mode": "rule_agent",
        "expected_rag_found": True,
        "expected_rag_source": "docs/knowledge/shipping-policy.md",
    },
    {
        "name": "\u8ba2\u5355\u5f02\u5e38\u591a\u5de5\u5177\u5904\u7406",
        "messages": ["\u6211\u7684\u8ba2\u5355 A101 48\u5c0f\u65f6\u4e86\uff0c\u600e\u4e48\u8fd8\u6ca1\u53d1\u8d27"],
        "expected_intent": "order_issue",
        "expected_execution_mode": "langgraph_agent",
        "expected_langgraph_tool": "handle_order_issue",
        "expected_rag_found": True,
        "expected_reply_keywords": ["\u8ba2\u5355 A101", "\u5efa\u8bae"],
    },
    {
        "name": "\u7269\u6d41\u5f02\u5e38 LangGraph \u5904\u7406",
        "messages": ["\u6211\u7684\u7269\u6d41 L101 48\u5c0f\u65f6\u4e86\uff0c\u600e\u4e48\u8fd8\u6ca1\u66f4\u65b0"],
        "expected_intent": "logistics_issue",
        "expected_execution_mode": "langgraph_agent",
        "expected_langgraph_tool": "handle_logistics_issue",
        "expected_rag_found": True,
        "expected_reply_keywords": ["\u7269\u6d41\u5355 L101", "\u5efa\u8bae"],
    },
    {
        "name": "LangGraph \u786e\u8ba4\u521b\u5efa\u6295\u8bc9",
        "messages": [
            "\u6211\u7684\u8ba2\u5355 A101 48\u5c0f\u65f6\u4e86\uff0c\u600e\u4e48\u8fd8\u6ca1\u53d1\u8d27",
            "\u786e\u8ba4\u521b\u5efa\u6295\u8bc9",
        ],
        "expected_intent": "confirm_create_complaint",
        "expected_execution_mode": "langgraph_agent",
        "expected_langgraph_nodes": ["check_pending_confirmation", "create_complaint"],
        "expected_reply_keywords": ["\u6295\u8bc9\u7f16\u53f7"],
    },
    {
        "name": "\u53d6\u6d88\u521b\u5efa\u6295\u8bc9",
        "messages": [
            "\u6211\u7684\u7269\u6d41 L101 48\u5c0f\u65f6\u4e86\uff0c\u600e\u4e48\u8fd8\u6ca1\u66f4\u65b0",
            "\u53d6\u6d88\u521b\u5efa\u6295\u8bc9",
        ],
        "expected_intent": "cancel_create_complaint",
        "expected_execution_mode": "rule_agent",
        "expected_reply_keywords": ["\u5df2\u53d6\u6d88\u521b\u5efa\u6295\u8bc9"],
    },
    {
        "name": "\u666e\u901a\u95ee\u5019\u4e0d\u8bef\u5efa\u6295\u8bc9",
        "messages": ["\u4f60\u597d"],
        "expected_intent": "unknown",
        "expected_execution_mode": "rule_agent",
        "expected_reply_keywords": ["\u6211\u53ea\u80fd\u67e5\u8be2\u8ba2\u5355\u6216\u7269\u6d41"],
    },
]


def check_agent_eval_case(case: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    trace = result.get("trace", {})
    reply = result.get("reply", "")
    rag = trace.get("rag") or {}
    failures = []

    expected_intent = case.get("expected_intent")
    if expected_intent and trace.get("intent") != expected_intent:
        failures.append(f"expected intent {expected_intent}, got {trace.get('intent')}")

    expected_execution_mode = case.get("expected_execution_mode")
    if expected_execution_mode and trace.get("execution_mode") != expected_execution_mode:
        failures.append(f"expected execution mode {expected_execution_mode}, got {trace.get('execution_mode')}")

    expected_langgraph_tool = case.get("expected_langgraph_tool")
    if expected_langgraph_tool:
        langgraph_trace = trace.get("langgraph") or {}
        if langgraph_trace.get("tool_selected") != expected_langgraph_tool:
            failures.append(
                f"expected langgraph tool {expected_langgraph_tool}, got {langgraph_trace.get('tool_selected')}"
            )

    expected_langgraph_nodes = case.get("expected_langgraph_nodes")
    if expected_langgraph_nodes:
        langgraph_trace = trace.get("langgraph") or {}
        if langgraph_trace.get("nodes") != expected_langgraph_nodes:
            failures.append(
                f"expected langgraph nodes {expected_langgraph_nodes}, got {langgraph_trace.get('nodes')}"
            )

    for keyword in case.get("expected_reply_keywords", []):
        if keyword not in reply:
            failures.append(f"reply missing keyword: {keyword}")

    if "expected_rag_found" in case and rag.get("found") != case["expected_rag_found"]:
        failures.append(f"expected rag found {case['expected_rag_found']}, got {rag.get('found')}")

    expected_source = case.get("expected_rag_source")
    if expected_source and expected_source not in (rag.get("sources") or []):
        failures.append(f"rag source missing: {expected_source}")

    return {
        "passed": not failures,
        "failures": failures,
    }


def run_agent_evaluation() -> Dict[str, Any]:
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = False
    try:
        return run_deterministic_agent_evaluation()
    finally:
        settings.llm_enabled = original_llm_enabled


def run_deterministic_agent_evaluation() -> Dict[str, Any]:
    cases = []
    passed_count = 0

    for index, case in enumerate(AGENT_EVAL_CASES, start=1):
        user_id = f"agent-eval-{index}"
        final_result = None
        for message in case["messages"]:
            final_result = run_agent_with_steps(ChatRequest(user_id=user_id, message=message, role="agent"))

        check = check_agent_eval_case(case, final_result or {})
        if check["passed"]:
            passed_count += 1

        trace = (final_result or {}).get("trace", {})
        cases.append({
            "name": case["name"],
            "messages": case["messages"],
            "expected_intent": case.get("expected_intent"),
            "actual_intent": trace.get("intent"),
            "expected_execution_mode": case.get("expected_execution_mode"),
            "reply": (final_result or {}).get("reply", ""),
            "reply_source": trace.get("reply_source"),
            "execution_mode": trace.get("execution_mode"),
            "langgraph_tool": (trace.get("langgraph") or {}).get("tool_selected"),
            "langgraph_nodes": (trace.get("langgraph") or {}).get("nodes", []),
            "decision_path": trace.get("decision_path", []),
            "rag_found": (trace.get("rag") or {}).get("found"),
            "rag_sources": (trace.get("rag") or {}).get("sources", []),
            "passed": check["passed"],
            "failures": check["failures"],
        })

    total = len(cases)
    return {
        "total": total,
        "passed": passed_count,
        "failed": total - passed_count,
        "pass_rate": round(passed_count / total, 4) if total else 0,
        "cases": cases,
    }
