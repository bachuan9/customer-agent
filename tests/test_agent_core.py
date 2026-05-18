from app.models.schemas import ChatRequest
from app.core.config import settings
from app.services.agent import (
    can_role_execute_tool,
    run_agent,
    run_agent_with_steps,
    set_pending_llm_action,
)
from app.services.llm_client import LLMClientError
from app.services.llm_reply import LLMReplyError
from app.services.llm_agent import build_messages, extract_first_tool_call
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
