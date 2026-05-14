from app.services.agent import format_llm_tool_selection_reply
from app.services.tool_registry import list_function_calling_tools
from app.services.tools import search_knowledge
from app.storage.db import insert_knowledge_article


def test_search_knowledge_finds_return_policy_sections():
    result = search_knowledge("7 天后还能退货吗")

    assert result["found"] is True
    assert "docs/knowledge/return-policy.md" in result["sources"]
    assert any("7 天" in match["content"] or "超过 7 天" in match["content"] for match in result["matches"])


def test_search_knowledge_finds_shipping_fee_policy():
    result = search_knowledge("质量问题退货运费谁承担")

    assert result["found"] is True
    assert any("运费" in match["content"] or "质量问题" in match["content"] for match in result["matches"])


def test_search_knowledge_finds_refund_timing_policy():
    result = search_knowledge("退款多久到账")

    assert result["found"] is True
    assert any("1 到 3 个工作日" in match["content"] or "退款" in match["content"] for match in result["matches"])


def test_search_knowledge_finds_shipping_policy():
    result = search_knowledge("物流超过48小时没有更新怎么办")

    assert result["found"] is True
    assert "docs/knowledge/shipping-policy.md" in result["sources"]


def test_search_knowledge_finds_membership_policy():
    result = search_knowledge("会员积分退款后会扣回吗")

    assert result["found"] is True
    assert "docs/knowledge/membership-policy.md" in result["sources"]


def test_search_knowledge_is_available_as_function_calling_tool():
    tools = list_function_calling_tools()
    names = [tool["function"]["name"] for tool in tools]

    assert "search_knowledge" in names


def test_knowledge_template_reply_includes_source():
    result = search_knowledge("退款多久到账")
    reply = format_llm_tool_selection_reply(
        {
            "tool_name": "search_knowledge",
            "arguments": {"query": "退款多久到账"},
            "tool_result": result,
            "requires_confirmation": False,
        }
    )

    assert "参考来源：" in reply
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
