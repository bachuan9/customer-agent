from fastapi.testclient import TestClient

from app.main import app
from app.services.langgraph_agent import run_langgraph_agent


client = TestClient(app)


def test_run_langgraph_agent_calls_tool_for_policy_question():
    result = run_langgraph_agent("物流 48 小时没有更新怎么办")

    assert result["trace"]["framework"] == "langgraph"
    assert result["trace"]["nodes"] == ["select_tool", "call_tool"]
    assert result["trace"]["tool_selected"] == "search_knowledge"
    assert result["trace"]["tool_used"] is True
    assert result["tool_result"]["found"] is True
    assert result["reply"]


def test_run_langgraph_agent_returns_no_tool_reply_when_no_tool_matches():
    result = run_langgraph_agent("你好")

    assert result["trace"]["framework"] == "langgraph"
    assert result["trace"]["nodes"] == ["select_tool", "no_tool_reply"]
    assert result["trace"]["tool_selected"] is None
    assert result["trace"]["tool_used"] is False
    assert result["trace"]["reason"] == "no_tool_selected"
    assert result["tool_result"] is None


def test_langgraph_agent_endpoint_returns_trace():
    response = client.post(
        "/langgraph/agent",
        json={"question": "退货后多久退款"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["trace"]["framework"] == "langgraph"
    assert data["trace"]["nodes"][0] == "select_tool"
    assert data["trace"]["tool_selected"] == "search_knowledge"
    assert data["tool_result"]["found"] is True
