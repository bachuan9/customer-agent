from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.langchain_agent import (
    LangChainAgentSelectionError,
    parse_tool_selection_response,
    run_langchain_agent,
    select_langchain_tool,
)
from app.services.llm_client import LLMClientError


client = TestClient(app)


def test_select_langchain_tool_selects_knowledge_for_policy_question():
    assert select_langchain_tool("物流 48 小时没有更新怎么办") == "search_knowledge"
    assert select_langchain_tool("退货后多久退款") == "search_knowledge"


def test_select_langchain_tool_returns_none_when_no_tool_matches():
    assert select_langchain_tool("你好") is None


def test_parse_tool_selection_response_accepts_search_knowledge():
    response = {
        "choices": [
            {
                "message": {
                    "content": '{"tool_name":"search_knowledge","arguments":{"query":"物流 48 小时没有更新怎么办"}}'
                }
            }
        ]
    }

    selection = parse_tool_selection_response(response, "物流问题")

    assert selection == {
        "tool_name": "search_knowledge",
        "arguments": {"query": "物流 48 小时没有更新怎么办"},
    }


def test_parse_tool_selection_response_rejects_invalid_json():
    response = {"choices": [{"message": {"content": "not json"}}]}

    try:
        parse_tool_selection_response(response, "你好")
    except LangChainAgentSelectionError as exc:
        assert "valid tool selection JSON" in str(exc)
    else:
        raise AssertionError("expected LangChainAgentSelectionError")


def test_run_langchain_agent_uses_llm_tool_selection_when_available(monkeypatch):
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = True

    def fake_call_llm(messages, tools=None):
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"tool_name":"search_knowledge","arguments":{"query":"物流 48 小时没有更新怎么办"}}'
                    }
                }
            ]
        }

    monkeypatch.setattr("app.services.langchain_agent.call_llm", fake_call_llm)

    try:
        result = run_langchain_agent("物流 48 小时没有更新怎么办")
    finally:
        settings.llm_enabled = original_llm_enabled

    assert result["trace"]["agent_mode"] == "llm_tool_selection"
    assert result["trace"]["tool_selected"] == "search_knowledge"
    assert result["trace"]["tool_used"] is True
    assert result["trace"]["tool_selection_fallback_reason"] is None
    assert result["tool_result"]["found"] is True


def test_run_langchain_agent_uses_llm_tool_arguments(monkeypatch):
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = True

    def fake_call_llm(messages, tools=None):
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"tool_name":"search_knowledge","arguments":{"query":"48 物流"}}'
                    }
                }
            ]
        }

    monkeypatch.setattr("app.services.langchain_agent.call_llm", fake_call_llm)

    try:
        result = run_langchain_agent("请帮我处理这个超时问题")
    finally:
        settings.llm_enabled = original_llm_enabled

    assert result["trace"]["tool_arguments"] == {"query": "48 物流"}
    assert result["tool_result"]["query"] == "48 物流"
    assert result["tool_result"]["found"] is True


def test_run_langchain_agent_falls_back_to_rules_when_llm_selection_fails(monkeypatch):
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = True

    def fake_call_llm(messages, tools=None):
        raise LLMClientError("mock selector unavailable")

    monkeypatch.setattr("app.services.langchain_agent.call_llm", fake_call_llm)

    try:
        result = run_langchain_agent("物流 48 小时没有更新怎么办")
    finally:
        settings.llm_enabled = original_llm_enabled

    assert result["trace"]["agent_mode"] == "deterministic_tool_selection"
    assert result["trace"]["tool_selected"] == "search_knowledge"
    assert result["trace"]["tool_selection_fallback_reason"] == "mock selector unavailable"
    assert result["tool_result"]["found"] is True


def test_run_langchain_agent_returns_no_tool_reply_when_no_tool_matches():
    result = run_langchain_agent("你好")

    assert result["trace"]["tool_selected"] is None
    assert result["trace"]["tool_used"] is False
    assert result["trace"]["reason"] == "no_tool_selected"
    assert result["tool_result"] is None


def test_langchain_agent_endpoint_returns_trace():
    response = client.post(
        "/langchain/agent",
        json={"question": "退货后多久退款"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["trace"]["framework"] == "langchain"
    assert data["trace"]["tool_selected"] == "search_knowledge"
    assert data["tool_result"]["found"] is True
