from app.models.schemas import ChatRequest
from app.services.agent import (
    can_role_execute_tool,
    run_agent,
    set_pending_llm_action,
)
from app.services.llm_agent import extract_first_tool_call
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


def test_rbac_manager_can_update_order_but_agent_cannot():
    assert can_role_execute_tool("manager", "update_order") is True
    assert can_role_execute_tool("agent", "update_order") is False


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
