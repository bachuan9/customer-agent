from app.services.agent import format_llm_tool_selection_reply
from app.services.tool_registry import list_function_calling_tools
from app.services.tools import search_knowledge
from app.storage.db import insert_knowledge_article


def test_search_knowledge_finds_return_policy_sections():
    result = search_knowledge("7 \u9000\u8d27")

    assert result["found"] is True
    assert "docs/knowledge/return-policy.md" in result["sources"]
    assert any("7" in match["content"] for match in result["matches"])


def test_search_knowledge_finds_shipping_policy():
    result = search_knowledge("48 \u7269\u6d41")

    assert result["found"] is True
    assert "docs/knowledge/shipping-policy.md" in result["sources"]


def test_search_knowledge_ignores_low_relevance_matches():
    result = search_knowledge("x")

    assert result["found"] is False
    assert result["matches"] == []
    assert result["sources"] == []


def test_search_knowledge_returns_match_explanations():
    result = search_knowledge("48 \u7269\u6d41")

    assert result["found"] is True
    first_match = result["matches"][0]
    assert first_match["score"] >= 3
    assert isinstance(first_match["matched_keywords"], list)
    assert "content" in first_match
    assert "source" in first_match


def test_search_knowledge_is_available_as_function_calling_tool():
    tools = list_function_calling_tools()
    names = [tool["function"]["name"] for tool in tools]

    assert "search_knowledge" in names


def test_knowledge_template_reply_includes_source():
    result = search_knowledge("7 \u9000\u8d27")
    reply = format_llm_tool_selection_reply(
        {
            "tool_name": "search_knowledge",
            "arguments": {"query": "7 \u9000\u8d27"},
            "tool_result": result,
            "requires_confirmation": False,
        }
    )

    assert "docs/knowledge/return-policy.md" in reply


def test_search_knowledge_finds_database_article():
    insert_knowledge_article(
        "fresh damaged compensation",
        "fresh damaged goods can request compensation within 24 hours",
        "fresh,compensation",
    )

    result = search_knowledge("fresh damaged compensation")

    assert result["found"] is True
    assert "knowledge_articles:" in result["sources"][0]
    assert any("fresh damaged compensation" in match["content"] for match in result["matches"])
