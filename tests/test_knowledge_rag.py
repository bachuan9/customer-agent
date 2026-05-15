from app.services.agent import format_llm_tool_selection_reply
from app.services.tool_registry import list_function_calling_tools
from app.services.tools import extract_knowledge_keywords, search_knowledge
from app.storage.db import insert_knowledge_article


def test_search_knowledge_finds_return_policy_sections():
    result = search_knowledge("7 退货")

    assert result["found"] is True
    assert "docs/knowledge/return-policy.md" in result["sources"]
    assert any("7" in match["content"] for match in result["matches"])


def test_search_knowledge_finds_shipping_policy():
    result = search_knowledge("48 物流")

    assert result["found"] is True
    assert "docs/knowledge/shipping-policy.md" in result["sources"]


def test_extract_knowledge_keywords_uses_grouped_keywords():
    keywords = extract_knowledge_keywords("物流48小时没更新超时")

    assert "物流" in keywords
    assert "48小时" in keywords
    assert "没更新" in keywords
    assert "超时" in keywords


def test_extract_knowledge_keywords_supports_membership_terms():
    keywords = extract_knowledge_keywords("会员积分优惠券")

    assert "会员" in keywords
    assert "积分" in keywords
    assert "优惠券" in keywords


def test_search_knowledge_ignores_low_relevance_matches():
    result = search_knowledge("x")

    assert result["found"] is False
    assert result["matches"] == []
    assert result["sources"] == []


def test_search_knowledge_does_not_match_without_business_keywords():
    result = search_knowledge("平台支持虚拟币提现吗")

    assert result["found"] is False
    assert result["matches"] == []
    assert result["sources"] == []


def test_knowledge_template_reply_refuses_when_no_reliable_answer():
    result = search_knowledge("x")
    reply = format_llm_tool_selection_reply(
        {
            "tool_name": "search_knowledge",
            "arguments": {"query": "x"},
            "tool_result": result,
            "requires_confirmation": False,
        }
    )

    assert "可靠" in reply
    assert "避免误导" in reply
    assert "转人工客服" in reply
    assert "主管确认" in reply


def test_search_knowledge_returns_match_explanations():
    result = search_knowledge("48 物流")

    assert result["found"] is True
    first_match = result["matches"][0]
    assert first_match["score"] >= 3
    assert isinstance(first_match["matched_keywords"], list)
    assert "shipping" in first_match["matched_groups"]
    assert "content" in first_match
    assert "source" in first_match


def test_search_knowledge_is_available_as_function_calling_tool():
    tools = list_function_calling_tools()
    names = [tool["function"]["name"] for tool in tools]

    assert "search_knowledge" in names


def test_knowledge_template_reply_includes_source():
    result = search_knowledge("7 退货")
    reply = format_llm_tool_selection_reply(
        {
            "tool_name": "search_knowledge",
            "arguments": {"query": "7 退货"},
            "tool_result": result,
            "requires_confirmation": False,
        }
    )

    assert "docs/knowledge/return-policy.md" in reply


def test_search_knowledge_finds_database_article():
    insert_knowledge_article(
        "生鲜破损赔付规则",
        "如果用户收到生鲜商品后发现破损，可以在签收后 24 小时内提交照片申请赔付。",
        "生鲜,赔付",
    )

    result = search_knowledge("生鲜破损怎么赔付")

    assert result["found"] is True
    assert "knowledge_articles:" in result["sources"][0]
    assert any("生鲜破损赔付规则" in match["content"] for match in result["matches"])
