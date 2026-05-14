from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.storage.db import insert_tool_call_log


client = TestClient(app)


def login_token(username: str, password: str) -> str:
    response = client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )
    return response.json()["token"]


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


def test_tool_logs_endpoint_supports_source_and_success_filters():
    insert_tool_call_log(
        "query_order",
        {"order_no": "A101"},
        {"found": True},
        True,
        source="llm_agent",
    )
    insert_tool_call_log(
        "update_order",
        {"order_no": "A101", "status": "delivered"},
        {"error": "permission_denied"},
        False,
        "permission_denied",
        "rbac_denied",
    )

    response = client.get("/tool-logs?source=rbac_denied&success=false")

    assert response.status_code == 200
    logs = response.json()
    assert len(logs) == 1
    assert logs[0]["source"] == "rbac_denied"
    assert logs[0]["success"] is False


def test_login_success_and_auth_me():
    login_response = client.post(
        "/auth/login",
        json={"username": "manager1", "password": "manager123"},
    )

    assert login_response.status_code == 200
    data = login_response.json()
    assert data["user"]["username"] == "manager1"
    assert data["user"]["role"] == "manager"
    assert data["token"]

    me_response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {data['token']}"},
    )

    assert me_response.status_code == 200
    assert me_response.json()["username"] == "manager1"
    assert me_response.json()["role"] == "manager"


def test_login_rejects_wrong_password():
    response = client.post(
        "/auth/login",
        json={"username": "manager1", "password": "wrong-password"},
    )

    assert response.status_code == 401


def test_logout_invalidates_token():
    login_response = client.post(
        "/auth/login",
        json={"username": "agent1", "password": "agent123"},
    )
    token = login_response.json()["token"]

    logout_response = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    me_response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert logout_response.status_code == 200
    assert logout_response.json() == {"logged_out": True}
    assert me_response.status_code == 401


def test_chat_uses_token_role_instead_of_request_role():
    login_response = client.post(
        "/auth/login",
        json={"username": "manager1", "password": "manager123"},
    )
    token = login_response.json()["token"]

    from app.services.agent import set_pending_llm_action

    set_pending_llm_action(
        "manager1",
        {
            "type": "pending_llm_action",
            "tool_name": "update_order",
            "arguments": {"order_no": "A101", "status": "shipped"},
        },
    )

    response = client.post(
        "/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "user_id": "fake-user",
            "message": "确认执行",
            "role": "agent",
        },
    )

    assert response.status_code == 200
    assert "订单 A101 已为您更新为" in response.json()["reply"]


def test_knowledge_article_crud_endpoints():
    token = login_token("manager1", "manager123")
    headers = {"Authorization": f"Bearer {token}"}
    create_response = client.post(
        "/knowledge",
        headers=headers,
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
        headers=headers,
        json={"title": "测试知识已更新", "enabled": False},
    )

    assert update_response.status_code == 200
    assert update_response.json()["title"] == "测试知识已更新"
    assert update_response.json()["enabled"] is False

    delete_response = client.delete(f"/knowledge/{article['id']}", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True, "id": article["id"]}


def test_knowledge_article_list_supports_query_and_tag_filters():
    token = login_token("manager1", "manager123")
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/knowledge",
        headers=headers,
        json={
            "title": "生鲜破损赔付规则",
            "content": "生鲜商品破损后可以申请赔付。",
            "tags": "生鲜,赔付",
            "enabled": True,
        },
    )
    client.post(
        "/knowledge",
        headers=headers,
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


def test_knowledge_write_requires_login():
    response = client.post(
        "/knowledge",
        json={
            "title": "未登录知识",
            "content": "未登录不能新增。",
            "tags": "auth",
            "enabled": True,
        },
    )

    assert response.status_code == 401


def test_knowledge_write_requires_manager_role():
    token = login_token("agent1", "agent123")

    response = client.post(
        "/knowledge",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "普通客服知识",
            "content": "普通客服不能新增。",
            "tags": "auth",
            "enabled": True,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "required role: manager"


def test_manager_can_list_users():
    token = login_token("manager1", "manager123")

    response = client.get(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    users = response.json()
    assert any(user["username"] == "agent1" for user in users)
    assert "password_hash" not in users[0]
    assert "token" not in users[0]


def test_agent_cannot_list_users():
    token = login_token("agent1", "agent123")

    response = client.get(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "required role: manager"


def test_manager_can_create_user():
    token = login_token("manager1", "manager123")
    username = "pytest_agent_create"

    response = client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": username,
            "password": "agent123",
            "display_name": "Pytest Agent",
            "role": "agent",
        },
    )

    assert response.status_code in {200, 409}
    if response.status_code == 200:
        data = response.json()
        assert data["username"] == username
        assert data["role"] == "agent"
        assert "password_hash" not in data


def test_create_user_rejects_duplicate_username():
    token = login_token("manager1", "manager123")

    response = client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": "agent1",
            "password": "agent123",
            "display_name": "Duplicate Agent",
            "role": "agent",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "user already exists"


def test_create_user_rejects_invalid_role():
    token = login_token("manager1", "manager123")

    response = client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": "pytest_invalid_role",
            "password": "agent123",
            "display_name": "Invalid Role",
            "role": "admin",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid user role"


def test_manager_can_update_user_role():
    token = login_token("manager1", "manager123")
    username = "pytest_role_update"
    client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": username,
            "password": "agent123",
            "display_name": "Role Update User",
            "role": "agent",
        },
    )

    response = client.patch(
        f"/users/{username}/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "manager"},
    )

    assert response.status_code == 200
    assert response.json()["username"] == username
    assert response.json()["role"] == "manager"


def test_update_user_role_returns_404_for_missing_user():
    token = login_token("manager1", "manager123")

    response = client.patch(
        "/users/not_exists_pytest/role",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "manager"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "user not found"


def test_manager_can_disable_and_enable_user():
    token = login_token("manager1", "manager123")
    username = "pytest_active_update"
    client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": username,
            "password": "agent123",
            "display_name": "Active Update User",
            "role": "agent",
        },
    )

    disable_response = client.patch(
        f"/users/{username}/active",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_active": False},
    )
    disabled_login_response = client.post(
        "/auth/login",
        json={"username": username, "password": "agent123"},
    )
    enable_response = client.patch(
        f"/users/{username}/active",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_active": True},
    )

    assert disable_response.status_code == 200
    assert disable_response.json()["is_active"] is False
    assert disabled_login_response.status_code == 401
    assert enable_response.status_code == 200
    assert enable_response.json()["is_active"] is True


def test_update_user_active_requires_manager_role():
    token = login_token("agent1", "agent123")

    response = client.patch(
        "/users/agent1/active",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_active": False},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "required role: manager"


def test_manager_can_reset_user_password():
    token = login_token("manager1", "manager123")
    username = "pytest_password_reset"
    client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": username,
            "password": "old-password",
            "display_name": "Password Reset User",
            "role": "agent",
        },
    )

    reset_response = client.patch(
        f"/users/{username}/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": "new-password"},
    )
    old_login_response = client.post(
        "/auth/login",
        json={"username": username, "password": "old-password"},
    )
    new_login_response = client.post(
        "/auth/login",
        json={"username": username, "password": "new-password"},
    )

    assert reset_response.status_code == 200
    assert reset_response.json()["username"] == username
    assert old_login_response.status_code == 401
    assert new_login_response.status_code == 200
    assert new_login_response.json()["user"]["username"] == username


def test_reset_user_password_requires_manager_role():
    token = login_token("agent1", "agent123")

    response = client.patch(
        "/users/agent1/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": "new-password"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "required role: manager"
