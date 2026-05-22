from fastapi.testclient import TestClient

from app.main import app
from app.services.langgraph_agent import assess_risk_level, run_langgraph_agent


client = TestClient(app)


def fake_select_tool_with_llm_fallback(question: str) -> dict:
    normalized_question = question.replace(" ", "")
    if any(keyword in normalized_question for keyword in ["物流", "退款", "退货", "48小时"]):
        return {
            "tool_name": "search_knowledge",
            "arguments": {"query": question},
            "agent_mode": "test_tool_selection",
            "fallback_reason": None,
        }
    return {
        "tool_name": None,
        "arguments": {},
        "agent_mode": "test_tool_selection",
        "fallback_reason": None,
    }


def fake_run_langchain_rag_agent(question: str) -> dict:
    return {
        "reply": "根据知识库，物流超过 48 小时没有更新时，可以联系客服核实并升级处理。",
        "trace": {
            "reply_source": "test_rag",
            "llm_used": False,
            "fallback_reason": None,
        },
        "knowledge_result": {
            "found": True,
            "title": "物流超时政策",
            "source": "test",
        },
    }


def fake_handle_order_issue(order_no: str, query: str) -> dict:
    return {
        "found": True,
        "order_no": order_no,
        "order_status": "paid",
        "tracking_no": "L101",
        "logistics_status": "pending",
        "knowledge_found": True,
        "suggest_complaint": True,
        "agent_suggestion": "建议核实订单是否超过承诺发货时效，并引导用户确认创建投诉。",
    }


def fake_handle_logistics_issue(tracking_no: str, query: str) -> dict:
    return {
        "found": True,
        "tracking_no": tracking_no,
        "order_no": "A101",
        "logistics_status": "pending",
        "knowledge_found": True,
        "suggest_complaint": True,
        "agent_suggestion": "建议联系仓库或承运商核实物流长时间未更新原因，并引导用户确认创建投诉。",
    }


def setup_fake_langgraph_dependencies(monkeypatch):
    monkeypatch.setattr(
        "app.services.langgraph_agent.select_tool_with_llm_fallback",
        fake_select_tool_with_llm_fallback,
    )
    monkeypatch.setattr(
        "app.services.langgraph_agent.run_langchain_rag_agent",
        fake_run_langchain_rag_agent,
    )
    monkeypatch.setattr(
        "app.services.langgraph_agent.handle_order_issue",
        fake_handle_order_issue,
    )
    monkeypatch.setattr(
        "app.services.langgraph_agent.handle_logistics_issue",
        fake_handle_logistics_issue,
    )


def test_run_langgraph_agent_routes_high_risk_to_confirmation(monkeypatch):
    setup_fake_langgraph_dependencies(monkeypatch)

    result = run_langgraph_agent("物流 48 小时没有更新怎么办", user_id="pytest-langgraph-high-risk")

    assert result["trace"]["framework"] == "langgraph"
    assert result["trace"]["nodes"] == [
        "check_pending_confirmation",
        "select_tool",
        "call_tool",
        "summarize_decision",
        "assess_risk",
        "confirm_complaint",
    ]
    assert result["trace"]["tool_selected"] == "search_knowledge"
    assert result["trace"]["tool_used"] is True
    assert result["trace"]["risk_level"] == "high"
    assert result["trace"]["requires_confirmation"] is True
    assert result["trace"]["confirmation_action"] == "create_complaint"
    assert result["trace"]["pending_saved"] is True
    assert result["decision_summary"]["selected_tool"] == "search_knowledge"
    assert "知识库" in result["decision_summary"]["why_this_tool"]
    assert result["tool_result"]["found"] is True
    assert "确认创建投诉" in result["reply"]


def test_run_langgraph_agent_creates_complaint_after_confirmation(monkeypatch):
    setup_fake_langgraph_dependencies(monkeypatch)
    user_id = "pytest-langgraph-confirm"

    first_result = run_langgraph_agent("物流 48 小时没有更新怎么办", user_id=user_id)
    second_result = run_langgraph_agent("确认创建投诉", user_id=user_id)

    assert first_result["trace"]["requires_confirmation"] is True
    assert second_result["trace"]["nodes"] == ["check_pending_confirmation", "create_complaint"]
    assert second_result["trace"]["confirmed_action"] == "create_complaint"
    assert second_result["trace"]["pending_cleared"] is True
    assert second_result["trace"]["complaint_id"]
    assert second_result["created_complaint"]["status"] == "created"
    assert "投诉编号" in second_result["reply"]


def test_run_langgraph_agent_uses_order_tool_when_order_no_exists(monkeypatch):
    setup_fake_langgraph_dependencies(monkeypatch)

    result = run_langgraph_agent("我的订单 A101 48小时了，怎么还没发货", user_id="pytest-langgraph-order")

    assert result["trace"]["nodes"] == [
        "check_pending_confirmation",
        "select_tool",
        "call_tool",
        "summarize_decision",
        "assess_risk",
        "confirm_complaint",
    ]
    assert result["trace"]["tool_selected"] == "handle_order_issue"
    assert result["trace"]["tool_arguments"]["order_no"] == "A101"
    assert result["trace"]["suggest_complaint"] is True
    assert result["trace"]["risk_level"] == "high"
    assert result["decision_summary"]["selected_tool"] == "handle_order_issue"
    assert "订单编号" in result["decision_summary"]["why_this_tool"]
    assert result["tool_result"]["order_no"] == "A101"
    assert "已查询到订单 A101" in result["reply"]


def test_run_langgraph_agent_uses_logistics_tool_when_tracking_no_exists(monkeypatch):
    setup_fake_langgraph_dependencies(monkeypatch)

    result = run_langgraph_agent("我的物流 L101 48小时了，怎么还没更新", user_id="pytest-langgraph-logistics")

    assert result["trace"]["nodes"] == [
        "check_pending_confirmation",
        "select_tool",
        "call_tool",
        "summarize_decision",
        "assess_risk",
        "confirm_complaint",
    ]
    assert result["trace"]["tool_selected"] == "handle_logistics_issue"
    assert result["trace"]["tool_arguments"]["tracking_no"] == "L101"
    assert result["trace"]["suggest_complaint"] is True
    assert result["trace"]["risk_level"] == "high"
    assert result["decision_summary"]["selected_tool"] == "handle_logistics_issue"
    assert "物流编号" in result["decision_summary"]["why_this_tool"]
    assert result["tool_result"]["tracking_no"] == "L101"
    assert "已查询到物流单 L101" in result["reply"]


def test_run_langgraph_agent_confirm_without_pending_does_not_create_complaint(monkeypatch):
    setup_fake_langgraph_dependencies(monkeypatch)

    result = run_langgraph_agent("确认创建投诉", user_id="pytest-langgraph-no-pending")

    assert result["trace"]["nodes"] == ["check_pending_confirmation", "select_tool", "no_tool_reply"]
    assert result["trace"]["has_pending_confirmation"] is False
    assert result["trace"]["is_confirm_message"] is True
    assert result["trace"]["tool_used"] is False
    assert result["trace"]["reason"] == "confirm_message_without_pending"
    assert result["created_complaint"] is None


def test_run_langgraph_agent_ends_after_normal_risk_policy_question(monkeypatch):
    setup_fake_langgraph_dependencies(monkeypatch)

    result = run_langgraph_agent("退货后多久退款", user_id="pytest-langgraph-normal")

    assert result["trace"]["nodes"] == [
        "check_pending_confirmation",
        "select_tool",
        "call_tool",
        "summarize_decision",
        "assess_risk",
    ]
    assert result["trace"]["tool_selected"] == "search_knowledge"
    assert result["trace"]["risk_level"] == "normal"
    assert result["decision_summary"]["selected_tool"] == "search_knowledge"
    assert "requires_confirmation" not in result["trace"]


def test_run_langgraph_agent_returns_no_tool_reply_when_no_tool_matches(monkeypatch):
    setup_fake_langgraph_dependencies(monkeypatch)

    result = run_langgraph_agent("你好", user_id="pytest-langgraph-no-tool")

    assert result["trace"]["framework"] == "langgraph"
    assert result["trace"]["nodes"] == ["check_pending_confirmation", "select_tool", "no_tool_reply"]
    assert result["trace"]["tool_selected"] is None
    assert result["trace"]["tool_used"] is False
    assert result["trace"]["reason"] == "no_tool_selected"
    assert result["trace"]["risk_level"] == "normal"
    assert result["tool_result"] is None


def test_assess_risk_level_detects_high_risk_keywords():
    assert assess_risk_level("物流 48 小时没有更新") == "high"
    assert assess_risk_level("商品破损需要赔付") == "high"
    assert assess_risk_level("普通退货政策") == "normal"


def test_langgraph_agent_endpoint_returns_trace(monkeypatch):
    setup_fake_langgraph_dependencies(monkeypatch)

    response = client.post(
        "/langgraph/agent",
        json={
            "user_id": "pytest-langgraph-api",
            "question": "物流 48 小时没有更新怎么办",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "pytest-langgraph-api"
    assert data["trace"]["framework"] == "langgraph"
    assert data["trace"]["nodes"] == [
        "check_pending_confirmation",
        "select_tool",
        "call_tool",
        "summarize_decision",
        "assess_risk",
        "confirm_complaint",
    ]
    assert data["trace"]["tool_selected"] == "search_knowledge"
    assert data["trace"]["requires_confirmation"] is True
    assert data["decision_summary"]["selected_tool"] == "search_knowledge"
    assert data["tool_result"]["found"] is True
