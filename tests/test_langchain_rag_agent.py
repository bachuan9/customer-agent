from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.llm_client import LLMClientError
from app.services.langchain_rag_agent import run_langchain_rag_agent


client = TestClient(app)


def test_langchain_rag_agent_uses_existing_knowledge_search():
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = False

    try:
        result = run_langchain_rag_agent("物流 48 小时没有更新怎么办")
    finally:
        settings.llm_enabled = original_llm_enabled

    assert result["knowledge_result"]["found"] is True
    assert result["trace"]["framework"] == "langchain"
    assert result["trace"]["chain"] == "PromptTemplate -> LLM/RunnableLambda"
    assert result["trace"]["rag_found"] is True
    assert result["trace"]["llm_used"] is False
    assert result["trace"]["reply_source"] == "langchain_template_fallback"
    assert "参考来源" in result["reply"]


def test_langchain_rag_agent_returns_safe_reply_when_not_found():
    result = run_langchain_rag_agent("平台支持虚拟币提现吗")

    assert result["knowledge_result"]["found"] is False
    assert result["trace"]["rag_found"] is False
    assert result["trace"]["llm_used"] is False
    assert result["trace"]["fallback_reason"] == "knowledge_not_found"
    assert "没有在知识库里找到可靠政策依据" in result["reply"]


def test_langchain_rag_endpoint_returns_trace_and_reply():
    response = client.post(
        "/langchain/rag",
        json={"question": "退货后多久退款"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["question"] == "退货后多久退款"
    assert data["trace"]["framework"] == "langchain"
    assert data["knowledge_result"]["found"] is True
    assert data["reply"]


def test_langchain_rag_agent_uses_llm_when_enabled(monkeypatch):
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = True

    def fake_call_llm(messages, tools=None):
        assert "知识库" in messages[0]["content"]
        assert "48" in messages[1]["content"]
        return {
            "choices": [
                {
                    "message": {
                        "content": "LLM 生成的客服回复：物流超过 48 小时未更新，建议联系客服核实。"
                    }
                }
            ]
        }

    monkeypatch.setattr("app.services.langchain_rag_agent.call_llm", fake_call_llm)

    try:
        result = run_langchain_rag_agent("物流 48 小时没有更新怎么办")
    finally:
        settings.llm_enabled = original_llm_enabled

    assert result["trace"]["llm_used"] is True
    assert result["trace"]["reply_source"] == "langchain_llm_reply"
    assert result["trace"]["fallback_reason"] is None
    assert result["reply"].startswith("LLM 生成的客服回复")


def test_langchain_rag_agent_falls_back_when_llm_fails(monkeypatch):
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = True

    def fake_call_llm(messages, tools=None):
        raise LLMClientError("mock llm unavailable")

    monkeypatch.setattr("app.services.langchain_rag_agent.call_llm", fake_call_llm)

    try:
        result = run_langchain_rag_agent("物流 48 小时没有更新怎么办")
    finally:
        settings.llm_enabled = original_llm_enabled

    assert result["trace"]["llm_used"] is False
    assert result["trace"]["reply_source"] == "langchain_template_fallback"
    assert result["trace"]["fallback_reason"] == "mock llm unavailable"
    assert "参考来源" in result["reply"]
