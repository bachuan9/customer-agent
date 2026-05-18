from app.services.agent import format_llm_tool_selection_reply
from app.services.tool_registry import list_function_calling_tools
from app.services.tools import (
    create_complaint,
    extract_knowledge_keywords,
    handle_logistics_issue,
    handle_order_issue,
    query_logistics_by_order,
    search_knowledge,
)
from app.storage.db import get_complaint_by_id, get_connection, insert_knowledge_article


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
    assert "物流配送" in first_match["match_reason"]
    assert "相关度分数" in first_match["match_reason"]
    assert "content" in first_match
    assert "source" in first_match


def test_search_knowledge_is_available_as_function_calling_tool():
    tools = list_function_calling_tools()
    names = [tool["function"]["name"] for tool in tools]

    assert "search_knowledge" in names


def test_handle_logistics_issue_is_available_as_function_calling_tool():
    tools = list_function_calling_tools()
    names = [tool["function"]["name"] for tool in tools]

    assert "handle_logistics_issue" in names


def test_create_complaint_supports_priority_and_handler():
    result = create_complaint("pytest-priority-user", "高风险投诉", priority="high", handler="客服主管")
    complaint = get_complaint_by_id(result["complaint_id"])

    assert result["status"] == "created"
    assert complaint["priority"] == "high"
    assert complaint["handler"] == "客服主管"
    assert complaint["follow_up_status"] == "高优先级请尽快处理"
    assert "24 小时" in complaint["follow_up_reason"]


def test_old_high_priority_complaint_needs_follow_up():
    result = create_complaint("pytest-old-priority-user", "很久没有处理的高风险投诉", priority="high", handler="客服主管")
    complaint_id = int(result["complaint_id"].split("-")[1])
    with get_connection() as conn:
        conn.execute(
            "UPDATE complaints SET created_at = ?, updated_at = NULL WHERE id = ?",
            ("2020-01-01T00:00:00Z", complaint_id),
        )
        conn.commit()

    complaint = get_complaint_by_id(result["complaint_id"])

    assert complaint["follow_up_status"] == "需要跟进"
    assert "超过 24 小时" in complaint["follow_up_reason"]


def test_handle_order_issue_is_available_as_function_calling_tool():
    tools = list_function_calling_tools()
    names = [tool["function"]["name"] for tool in tools]

    assert "handle_order_issue" in names


def test_handle_order_issue_combines_order_and_knowledge():
    result = handle_order_issue("A101", "我的订单 A101 48小时了，怎么还没发货")

    assert result["found"] is True
    assert result["order_no"] == "A101"
    assert result["order_status"] == "shipped"
    assert result["tracking_no"] == "L101"
    assert result["logistics_status"] == "delivered"
    assert result["knowledge_found"] is True
    assert result["suggest_complaint"] is True
    assert "签收信息" in result["agent_suggestion"]
    assert "调用工具：query_order" in result["steps"]
    assert "调用工具：query_logistics_by_order" in result["steps"]
    assert "调用工具：search_knowledge" in result["steps"]
    assert "生成客服处理建议" in result["steps"]


def test_query_logistics_by_order_finds_related_tracking_no():
    result = query_logistics_by_order("A101")

    assert result["found"] is True
    assert result["order_no"] == "A101"
    assert result["tracking_no"] == "L101"
    assert result["status"] == "delivered"


def test_handle_order_issue_template_reply_is_readable():
    result = handle_order_issue("A101", "我的订单 A101 48小时了，怎么还没发货")
    reply = format_llm_tool_selection_reply(
        {
            "tool_name": "handle_order_issue",
            "arguments": {"order_no": "A101", "query": "我的订单 A101 48小时了，怎么还没发货"},
            "tool_result": result,
            "requires_confirmation": False,
        }
    )

    assert "已同时查询订单状态和平台发货政策" in reply
    assert "订单 A101" in reply
    assert "关联物流 L101" in reply
    assert "客服处理建议" in reply
    assert "确认创建投诉" in reply


def test_handle_logistics_issue_combines_logistics_and_knowledge():
    result = handle_logistics_issue("L101", "我的物流 L101 48小时了，怎么还没发货")

    assert result["found"] is True
    assert result["tracking_no"] == "L101"
    assert result["order_no"] == "A101"
    assert result["logistics_status"] == "delivered"
    assert result["knowledge_found"] is True
    assert result["suggest_complaint"] is True
    assert "签收人" in result["agent_suggestion"]
    assert "调用工具：query_logistics" in result["steps"]
    assert "调用工具：search_knowledge" in result["steps"]
    assert "生成客服处理建议" in result["steps"]


def test_handle_logistics_issue_template_reply_is_readable():
    result = handle_logistics_issue("L101", "我的物流 L101 48小时了，怎么还没发货")
    reply = format_llm_tool_selection_reply(
        {
            "tool_name": "handle_logistics_issue",
            "arguments": {"tracking_no": "L101", "query": "我的物流 L101 48小时了，怎么还没发货"},
            "tool_result": result,
            "requires_confirmation": False,
        }
    )

    assert "已同时查询物流状态和平台政策" in reply
    assert "物流 L101" in reply
    assert "客服处理建议" in reply
    assert "确认创建投诉" in reply


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


def test_knowledge_template_reply_includes_match_reason():
    result = search_knowledge("48 物流")
    reply = format_llm_tool_selection_reply(
        {
            "tool_name": "search_knowledge",
            "arguments": {"query": "48 物流"},
            "tool_result": result,
            "requires_confirmation": False,
        }
    )

    assert "命中依据" in reply
    assert "物流配送" in reply


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
