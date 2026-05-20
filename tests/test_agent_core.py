from app.models.schemas import ChatRequest
from app.core.config import settings
from app.services.agent import (
    can_role_execute_tool,
    detect_intent,
    run_agent,
    run_agent_with_steps,
    set_pending_llm_action,
)
from app.services.llm_client import LLMClientError
from app.services.llm_reply import LLMReplyError
from app.services.llm_agent import LLMAgentError, build_messages, extract_first_tool_call
from app.storage.db import fetch_tool_call_logs, get_order_status


def test_extract_first_tool_call_parses_function_arguments():
    response = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "query_order",
                                "arguments": '{"order_no":"A101"}',
                            }
                        }
                    ]
                }
            }
        ]
    }

    tool_name, arguments = extract_first_tool_call(response)

    assert tool_name == "query_order"
    assert arguments == {"order_no": "A101"}


def test_llm_prompt_guides_logistics_issue_to_combined_tool():
    messages = build_messages("我的物流 L101 48小时了，怎么还没发货")
    system_prompt = messages[0]["content"]

    assert "handle_logistics_issue" in system_prompt
    assert "物流超时" in system_prompt
    assert "48小时未更新" in system_prompt
    assert "没发货" in system_prompt


def test_llm_prompt_guides_order_issue_to_combined_tool():
    messages = build_messages("我的订单 A101 48小时了，怎么还没发货")
    system_prompt = messages[0]["content"]

    assert "handle_order_issue" in system_prompt
    assert "订单超时" in system_prompt
    assert "48小时未发货" in system_prompt
    assert "还没发货" in system_prompt


def test_policy_question_is_detected_as_knowledge_search():
    assert detect_intent("物流超时政策") == "search_knowledge"
    assert detect_intent("会员积分规则") == "search_knowledge"


def test_follow_up_logistics_uses_recent_order_context():
    user_id = "pytest-follow-up-logistics"

    first = run_agent_with_steps(ChatRequest(user_id=user_id, message="查订单 A101", role="agent"))
    second = run_agent_with_steps(ChatRequest(user_id=user_id, message="那物流呢", role="agent"))

    assert "A101" in first["reply"]
    assert "物流 L101" in second["reply"]


def test_follow_up_order_uses_recent_logistics_context():
    user_id = "pytest-follow-up-order"

    first = run_agent_with_steps(ChatRequest(user_id=user_id, message="查物流 L101", role="agent"))
    second = run_agent_with_steps(ChatRequest(user_id=user_id, message="那订单呢", role="agent"))

    assert "L101" in first["reply"]
    assert "订单 A101" in second["reply"]


def test_rbac_manager_can_update_order_but_agent_cannot():
    assert can_role_execute_tool("manager", "update_order") is True
    assert can_role_execute_tool("agent", "update_order") is False


def test_run_agent_with_steps_shows_llm_execution_mode(monkeypatch):
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = True

    def fake_tool_selection(message):
        return {
            "tool_name": "query_order",
            "arguments": {"order_no": "A101"},
            "tool_result": {"found": True, "order_no": "A101", "status": "shipped"},
            "requires_confirmation": False,
        }

    def fake_llm_reply(message, selection):
        return "这是 LLM 润色后的订单回复。"

    monkeypatch.setattr("app.services.agent.run_llm_tool_selection", fake_tool_selection)
    monkeypatch.setattr("app.services.agent.generate_llm_reply", fake_llm_reply)

    try:
        result = run_agent_with_steps(ChatRequest(user_id="pytest-llm-steps", message="帮我查一下 A101", role="agent"))
    finally:
        settings.llm_enabled = original_llm_enabled

    assert result["reply"] == "这是 LLM 润色后的订单回复。"
    assert "执行模式：LLM Agent（本次调用了 LLM）" in result["steps"]
    assert "回复来源：LLM 润色生成" in result["steps"]
    assert "LLM 选择工具：query_order" in result["steps"]
    assert "LLM 生成最终回复" in result["steps"]
    assert result["trace"]["selection"]["arguments"] == {"order_no": "A101"}
    assert result["trace"]["selection"]["tool_result"]["status"] == "shipped"


def test_run_agent_with_steps_shows_llm_template_fallback_reply_source(monkeypatch):
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = True

    def fake_tool_selection(message):
        return {
            "tool_name": "query_order",
            "arguments": {"order_no": "A101"},
            "tool_result": {"found": True, "order_no": "A101", "status": "shipped"},
            "requires_confirmation": False,
        }

    def fake_llm_reply(message, selection):
        raise LLMReplyError("mock reply failed")

    monkeypatch.setattr("app.services.agent.run_llm_tool_selection", fake_tool_selection)
    monkeypatch.setattr("app.services.agent.generate_llm_reply", fake_llm_reply)

    try:
        result = run_agent_with_steps(ChatRequest(user_id="pytest-llm-template-fallback", message="帮我查一下 A101", role="agent"))
    finally:
        settings.llm_enabled = original_llm_enabled

    assert "订单 A101" in result["reply"]
    assert "执行模式：LLM Agent（本次调用了 LLM）" in result["steps"]
    assert "回复来源：LLM 工具结果模板" in result["steps"]
    assert "LLM 选择工具：query_order" in result["steps"]


    assert result["trace"]["llm_fallback_error"] == "mock reply failed"


def test_llm_search_knowledge_selection_populates_rag_trace(monkeypatch):
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = True

    def fake_tool_selection(message):
        return {
            "tool_name": "search_knowledge",
            "arguments": {"query": "\u7269\u6d41\u8d85\u65f6\u653f\u7b56"},
            "tool_result": {
                "found": True,
                "query": "\u7269\u6d41\u8d85\u65f6\u653f\u7b56",
                "matches": [
                    {
                        "content": "\u7269\u6d41\u8d85\u8fc7 48 \u5c0f\u65f6\u6ca1\u6709\u66f4\u65b0\uff0c\u53ef\u4ee5\u8054\u7cfb\u5ba2\u670d\u3002",
                        "source": "docs/knowledge/shipping-policy.md",
                        "score": 6.5,
                        "keyword_score": 6,
                        "embedding_score": 0.5,
                        "retrieval_mode": "hybrid_keyword_embedding",
                        "title": "\u7269\u6d41\u4e0e\u914d\u9001\u653f\u7b56",
                        "source_type": "markdown",
                        "match_reason": "\u76f8\u5173\u5ea6\u5206\u6570\uff1a6",
                    }
                ],
                "sources": ["docs/knowledge/shipping-policy.md"],
                "source": "docs/knowledge/shipping-policy.md",
            },
            "requires_confirmation": False,
        }

    def fake_llm_reply(message, selection):
        raise LLMReplyError("mock reply failed")

    monkeypatch.setattr("app.services.agent.run_llm_tool_selection", fake_tool_selection)
    monkeypatch.setattr("app.services.agent.generate_llm_reply", fake_llm_reply)

    try:
        result = run_agent_with_steps(ChatRequest(user_id="pytest-llm-rag-trace", message="\u7269\u6d41\u8d85\u65f6\u653f\u7b56", role="agent"))
    finally:
        settings.llm_enabled = original_llm_enabled

    assert result["trace"]["rag"]["found"] is True
    assert result["trace"]["rag"]["sources"] == ["docs/knowledge/shipping-policy.md"]
    assert result["trace"]["rag"]["retrieval_mode"] == "hybrid_keyword_embedding"
    assert result["trace"]["rag"]["keyword_score"] == 6
    assert result["trace"]["rag"]["embedding_score"] == 0.5
    assert result["trace"]["llm_fallback_error"] == "mock reply failed"



def test_policy_question_uses_rag_after_llm_tool_selection_fails(monkeypatch):
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = True

    def fake_tool_selection(message):
        raise LLMAgentError("LLM did not return a tool call")

    monkeypatch.setattr("app.services.agent.run_llm_tool_selection", fake_tool_selection)

    try:
        result = run_agent_with_steps(
            ChatRequest(
                user_id="pytest-policy-rag-fallback",
                message="\u7269\u6d41\u8d85\u65f6\u653f\u7b56",
                role="agent",
            )
        )
    finally:
        settings.llm_enabled = original_llm_enabled

    assert result["trace"]["intent"] == "search_knowledge"
    assert result["trace"]["execution_mode"] == "rule_agent"
    assert result["trace"]["rag"]["found"] is True
    assert "docs/knowledge/shipping-policy.md" in result["trace"]["rag"]["sources"]
    assert "\u6211\u53ea\u80fd\u67e5\u8be2\u8ba2\u5355\u6216\u7269\u6d41" not in result["reply"]


def test_policy_question_uses_rag_llm_reply_after_llm_tool_selection_fails(monkeypatch):
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = True

    def fake_tool_selection(message):
        raise LLMAgentError("LLM did not return a tool call")

    def fake_rag_llm_reply(message, knowledge_result):
        assert message == "\u7269\u6d41\u8d85\u65f6\u653f\u7b56"
        assert knowledge_result["found"] is True
        assert "docs/knowledge/shipping-policy.md" in knowledge_result["sources"]
        return "\u8fd9\u662f RAG \u547d\u4e2d\u540e LLM \u751f\u6210\u7684\u5ba2\u670d\u56de\u590d\u3002"

    monkeypatch.setattr("app.services.agent.run_llm_tool_selection", fake_tool_selection)
    monkeypatch.setattr("app.services.agent.generate_rag_llm_reply", fake_rag_llm_reply)

    try:
        result = run_agent_with_steps(
            ChatRequest(
                user_id="pytest-policy-rag-llm-reply",
                message="\u7269\u6d41\u8d85\u65f6\u653f\u7b56",
                role="agent",
            )
        )
    finally:
        settings.llm_enabled = original_llm_enabled

    assert result["reply"] == "\u8fd9\u662f RAG \u547d\u4e2d\u540e LLM \u751f\u6210\u7684\u5ba2\u670d\u56de\u590d\u3002"
    assert result["trace"]["llm_reply_generated"] is True
    assert result["trace"]["reply_source"] == "rag_llm_reply"
    assert result["trace"]["rag"]["found"] is True
    assert "\u56de\u590d\u6765\u6e90\uff1aRAG \u547d\u4e2d\u540e\u7531 LLM \u751f\u6210" in result["steps"]


def test_policy_question_falls_back_to_rag_template_when_rag_llm_reply_fails(monkeypatch):
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = True

    def fake_tool_selection(message):
        raise LLMAgentError("LLM did not return a tool call")

    def fake_rag_llm_reply(message, knowledge_result):
        raise LLMReplyError("mock rag reply failed")

    monkeypatch.setattr("app.services.agent.run_llm_tool_selection", fake_tool_selection)
    monkeypatch.setattr("app.services.agent.generate_rag_llm_reply", fake_rag_llm_reply)

    try:
        result = run_agent_with_steps(
            ChatRequest(
                user_id="pytest-policy-rag-llm-fallback",
                message="\u7269\u6d41\u8d85\u65f6\u653f\u7b56",
                role="agent",
            )
        )
    finally:
        settings.llm_enabled = original_llm_enabled

    assert result["trace"]["reply_source"] == "rule_template"
    assert result["trace"]["llm_fallback_error"] == "mock rag reply failed"
    assert "docs/knowledge/shipping-policy.md" in result["reply"]


def test_run_agent_with_steps_traces_confirmation_requirement(monkeypatch):
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = True

    def fake_tool_selection(message):
        return {
            "tool_name": "update_order",
            "arguments": {"order_no": "A101", "status": "delivered"},
            "tool_result": {"updated": True},
            "requires_confirmation": True,
        }

    monkeypatch.setattr("app.services.agent.run_llm_tool_selection", fake_tool_selection)

    try:
        result = run_agent_with_steps(ChatRequest(user_id="pytest-llm-confirm-trace", message="把订单 A101 改成 delivered", role="manager"))
    finally:
        settings.llm_enabled = original_llm_enabled

    assert "确认执行" in result["reply"]
    assert "保存待确认动作：pending_llm_action" in result["steps"]
    assert result["trace"]["selection"]["tool_name"] == "update_order"
    assert result["trace"]["selection"]["requires_confirmation"] is True


def test_run_agent_with_steps_shows_llm_fallback_reason(monkeypatch):
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = True

    def fake_tool_selection(message):
        raise LLMClientError("mock llm unavailable")

    monkeypatch.setattr("app.services.agent.run_llm_tool_selection", fake_tool_selection)

    try:
        result = run_agent_with_steps(ChatRequest(user_id="pytest-llm-fallback", message="查订单 A101", role="agent"))
    finally:
        settings.llm_enabled = original_llm_enabled

    assert "订单 A101" in result["reply"]
    assert "执行模式：规则 Agent（LLM 调用失败后自动降级）" in result["steps"]
    assert "LLM 降级原因：mock llm unavailable" in result["steps"]
    assert "调用工具：query_order" in result["steps"]


def test_agent_role_denied_confirmation_is_logged():
    user_id = "pytest-rbac-denied"
    set_pending_llm_action(
        user_id,
        {
            "type": "pending_llm_action",
            "tool_name": "update_order",
            "arguments": {"order_no": "A101", "status": "delivered"},
        },
    )

    reply = run_agent(ChatRequest(user_id=user_id, message="确认执行", role="agent"))
    latest_log = fetch_tool_call_logs(1)[0]

    assert "没有权限" in reply
    assert latest_log["source"] == "rbac_denied"
    assert latest_log["error"] == "permission_denied"
    assert latest_log["success"] is False


def test_manager_confirmation_executes_pending_action():
    user_id = "pytest-manager-confirm"
    set_pending_llm_action(
        user_id,
        {
            "type": "pending_llm_action",
            "tool_name": "update_order",
            "arguments": {"order_no": "A101", "status": "shipped"},
        },
    )

    reply = run_agent(ChatRequest(user_id=user_id, message="确认执行", role="manager"))
    latest_log = fetch_tool_call_logs(1)[0]

    assert "订单 A101 已为您更新为" in reply
    assert get_order_status("A101") == "shipped"
    assert latest_log["source"] == "llm_confirmed_action"
    assert latest_log["success"] is True
