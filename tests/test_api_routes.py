from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


client = TestClient(app)


def test_health_endpoint_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_endpoint_uses_rule_agent_when_llm_disabled():
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = False

    try:
        response = client.post(
            "/chat",
            json={
                "user_id": "pytest-api-chat",
                "message": "查订单 A101",
                "role": "agent",
            },
        )
    finally:
        settings.llm_enabled = original_llm_enabled

    assert response.status_code == 200
    assert "订单 A101" in response.json()["reply"]


def test_chat_endpoint_handles_logistics_issue_with_policy_when_llm_disabled():
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = False

    try:
        response = client.post(
            "/chat",
            json={
                "user_id": "pytest-api-logistics-issue",
                "message": "我的物流 L101 48小时了，怎么还没发货",
                "role": "agent",
            },
        )
    finally:
        settings.llm_enabled = original_llm_enabled

    reply = response.json()["reply"]
    assert response.status_code == 200
    assert "物流 L101" in reply
    assert "当前状态" in reply
    assert "物流异常处理规则" in reply
    assert "建议您" in reply
    assert "参考来源" in reply


def test_chat_endpoint_handles_order_issue_with_policy_when_llm_disabled():
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = False

    try:
        response = client.post(
            "/chat",
            json={
                "user_id": "pytest-api-order-issue",
                "message": "我的订单 A101 48小时了，怎么还没发货",
                "role": "agent",
            },
        )
    finally:
        settings.llm_enabled = original_llm_enabled

    reply = response.json()["reply"]
    assert response.status_code == 200
    assert "订单 A101" in reply
    assert "当前状态" in reply
    assert "发货时效规则" in reply
    assert "建议您" in reply
    assert "参考来源" in reply


def test_order_detail_endpoint_returns_order_status():
    response = client.get("/orders/A101")

    assert response.status_code == 200
    assert response.json()["order_no"] == "A101"
    assert "status" in response.json()


def test_missing_order_returns_404():
    response = client.get("/orders/NOT_EXISTS")

    assert response.status_code == 404
    assert response.json()["detail"] == "order not found"


def test_tool_log_stats_endpoint_includes_sources():
    response = client.get("/tool-logs/stats")
    data = response.json()

    assert response.status_code == 200
    assert "total" in data
    assert "success" in data
    assert "failed" in data
    assert "sources" in data
    assert isinstance(data["sources"], list)


def test_knowledge_article_crud_endpoints():
    create_response = client.post(
        "/knowledge",
        json={
            "title": "测试知识",
            "content": "这是用于接口测试的知识库内容。",
            "tags": "test",
            "enabled": True,
        },
    )

    assert create_response.status_code == 200
    article = create_response.json()
    assert article["title"] == "测试知识"
    assert article["enabled"] is True

    list_response = client.get("/knowledge")
    assert list_response.status_code == 200
    assert any(item["id"] == article["id"] for item in list_response.json())

    update_response = client.patch(
        f"/knowledge/{article['id']}",
        json={"title": "测试知识已更新", "enabled": False},
    )

    assert update_response.status_code == 200
    assert update_response.json()["title"] == "测试知识已更新"
    assert update_response.json()["enabled"] is False

    delete_response = client.delete(f"/knowledge/{article['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True, "id": article["id"]}


def test_knowledge_article_list_supports_query_and_tag_filters():
    client.post(
        "/knowledge",
        json={
            "title": "生鲜破损赔付规则",
            "content": "生鲜商品破损后可以申请赔付。",
            "tags": "生鲜,赔付",
            "enabled": True,
        },
    )
    client.post(
        "/knowledge",
        json={
            "title": "普通退款规则",
            "content": "退款通常 1 到 3 个工作日到账。",
            "tags": "退款,售后",
            "enabled": True,
        },
    )

    response = client.get("/knowledge?query=破损&tag=生鲜")

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["title"] == "生鲜破损赔付规则"
