from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.storage.db import insert_tool_call_log, save_chat_message


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
    assert "执行模式：规则 Agent（本次未调用 LLM）" in response.json()["steps"]
    assert "回复来源：规则模板" in response.json()["steps"]
    assert "调用工具：query_order" in response.json()["steps"]


def test_chat_endpoint_saves_user_and_agent_messages_to_history():
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = False
    user_id = "pytest-chat-history"

    try:
        response = client.post(
            "/chat",
            json={
                "user_id": user_id,
                "message": "查订单 A101",
                "role": "agent",
            },
        )
        history_response = client.get(f"/chat/history/{user_id}")
    finally:
        settings.llm_enabled = original_llm_enabled

    assert response.status_code == 200
    assert history_response.status_code == 200
    history = history_response.json()
    assert history[-2]["sender"] == "user"
    assert history[-2]["message"] == "查订单 A101"
    assert history[-1]["sender"] == "agent"
    assert history[-1]["message"] == response.json()["reply"]
    assert history[-1]["steps"] == response.json()["steps"]


def test_delete_chat_history_endpoint_clears_saved_messages():
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = False
    user_id = "pytest-clear-chat-history"

    try:
        chat_response = client.post(
            "/chat",
            json={
                "user_id": user_id,
                "message": "查订单 A101",
                "role": "agent",
            },
        )
        delete_response = client.delete(f"/chat/history/{user_id}")
        history_response = client.get(f"/chat/history/{user_id}")
    finally:
        settings.llm_enabled = original_llm_enabled

    assert chat_response.status_code == 200
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] >= 2
    assert delete_response.json()["session_cleared"] is True
    assert history_response.status_code == 200
    assert history_response.json() == []


def test_delete_chat_history_endpoint_clears_pending_agent_memory():
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = False
    user_id = "pytest-clear-chat-session-memory"

    try:
        issue_response = client.post(
            "/chat",
            json={
                "user_id": user_id,
                "message": "我的物流 L101 48小时了，怎么还没发货",
                "role": "agent",
            },
        )
        delete_response = client.delete(f"/chat/history/{user_id}")
        confirm_response = client.post(
            "/chat",
            json={
                "user_id": user_id,
                "message": "确认创建投诉",
                "role": "agent",
            },
        )
    finally:
        settings.llm_enabled = original_llm_enabled

    assert issue_response.status_code == 200
    assert "保存待确认动作：waiting_confirm" in issue_response.json()["steps"]
    assert delete_response.status_code == 200
    assert delete_response.json()["session_cleared"] is True
    assert confirm_response.status_code == 200
    assert "当前没有待确认创建的投诉" in confirm_response.json()["reply"]


def test_chat_sessions_endpoint_returns_latest_message_summary():
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = False

    try:
        first_response = client.post(
            "/chat",
            json={
                "user_id": "pytest-session-a",
                "message": "查订单 A101",
                "role": "agent",
            },
        )
        second_response = client.post(
            "/chat",
            json={
                "user_id": "pytest-session-b",
                "message": "查物流 L101",
                "role": "agent",
            },
        )
        sessions_response = client.get("/chat/sessions")
    finally:
        settings.llm_enabled = original_llm_enabled

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert sessions_response.status_code == 200
    sessions = sessions_response.json()
    session_by_user = {item["user_id"]: item for item in sessions}
    assert session_by_user["pytest-session-a"]["message_count"] >= 2
    assert session_by_user["pytest-session-b"]["last_sender"] == "agent"
    assert session_by_user["pytest-session-b"]["needs_reply"] is False
    assert "物流 L101" in session_by_user["pytest-session-b"]["last_message"]


def test_chat_sessions_endpoint_marks_user_last_message_as_needing_reply():
    user_id = "pytest-session-needs-reply"
    save_chat_message(user_id, "agent", "上一轮已回复")
    save_chat_message(user_id, "user", "我还有一个问题")

    response = client.get("/chat/sessions")

    assert response.status_code == 200
    session_by_user = {item["user_id"]: item for item in response.json()}
    assert session_by_user[user_id]["last_sender"] == "user"
    assert session_by_user[user_id]["needs_reply"] is True


def test_chat_sessions_endpoint_limits_agent_to_own_session():
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = False
    token = login_token("agent1", "agent123")

    try:
        own_response = client.post(
            "/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "user_id": "fake-user",
                "message": "查订单 A101",
                "role": "manager",
            },
        )
        other_response = client.post(
            "/chat",
            json={
                "user_id": "pytest-other-session",
                "message": "查物流 L101",
                "role": "agent",
            },
        )
        sessions_response = client.get(
            "/chat/sessions",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        settings.llm_enabled = original_llm_enabled

    assert own_response.status_code == 200
    assert other_response.status_code == 200
    assert sessions_response.status_code == 200
    sessions = sessions_response.json()
    assert sessions
    assert {item["user_id"] for item in sessions} == {"agent1"}


def test_manual_chat_reply_endpoint_saves_agent_message():
    user_id = "pytest-manual-reply"
    save_chat_message(user_id, "user", "请问我的订单怎么处理")

    response = client.post(
        f"/chat/history/{user_id}/reply",
        json={"message": "您好，客服正在为您核实订单状态。"},
    )
    history_response = client.get(f"/chat/history/{user_id}")

    assert response.status_code == 200
    assert response.json()["sender"] == "agent"
    assert response.json()["message"] == "您好，客服正在为您核实订单状态。"
    assert history_response.status_code == 200
    assert history_response.json()[-1]["sender"] == "agent"
    assert history_response.json()[-1]["steps"] == ["人工客服回复：保存到聊天历史"]


def test_manual_chat_reply_endpoint_rejects_empty_message():
    response = client.post(
        "/chat/history/pytest-empty-reply/reply",
        json={"message": "   "},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "reply message is required"


def test_agent_cannot_manually_reply_to_another_users_chat():
    token = login_token("agent1", "agent123")

    response = client.post(
        "/chat/history/other-user/reply",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "这是一条越权回复"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "cannot access another user's chat history"


def test_agent_cannot_access_another_users_chat_history_when_logged_in():
    token = login_token("agent1", "agent123")

    response = client.get(
        "/chat/history/other-user",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "cannot access another user's chat history"


def test_manager_can_access_another_users_chat_history_when_logged_in():
    token = login_token("manager1", "manager123")

    response = client.get(
        "/chat/history/agent1",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200


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
    steps = response.json()["steps"]
    assert response.status_code == 200
    assert "已同时查询物流状态和平台政策" in reply
    assert "物流 L101" in reply
    assert "当前状态" in reply
    assert "物流异常处理规则" in reply
    assert "建议您" in reply
    assert "参考来源" in reply
    assert "创建投诉" in reply
    assert "客服主管" in reply
    assert "识别意图：logistics_issue" in steps
    assert "执行模式：规则 Agent（本次未调用 LLM）" in steps
    assert "调用组合工具：handle_logistics_issue" in steps
    assert "内部调用：query_logistics" in steps
    assert "内部调用：search_knowledge" in steps
    assert "保存待确认动作：waiting_confirm" in steps


def test_chat_endpoint_logistics_issue_keeps_waiting_confirm_when_llm_enabled():
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = True

    try:
        response = client.post(
            "/chat",
            json={
                "user_id": "pytest-api-logistics-issue-llm-enabled",
                "message": "我的物流 L101 48小时了，怎么还没发货",
                "role": "agent",
            },
        )
    finally:
        settings.llm_enabled = original_llm_enabled

    steps = response.json()["steps"]
    assert response.status_code == 200
    assert "识别意图：logistics_issue" in steps
    assert "调用组合工具：handle_logistics_issue" in steps
    assert "内部调用：query_logistics" in steps
    assert "内部调用：search_knowledge" in steps
    assert "保存待确认动作：waiting_confirm" in steps


def test_chat_endpoint_confirms_logistics_issue_complaint_when_llm_disabled():
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = False

    try:
        issue_response = client.post(
            "/chat",
            json={
                "user_id": "pytest-confirm-logistics-complaint",
                "message": "我的物流 L101 48小时了，怎么还没发货",
                "role": "agent",
            },
        )
        confirm_response = client.post(
            "/chat",
            json={
                "user_id": "pytest-confirm-logistics-complaint",
                "message": "确认创建投诉",
                "role": "agent",
            },
        )
        list_response = client.get("/complaints")
    finally:
        settings.llm_enabled = original_llm_enabled

    assert issue_response.status_code == 200
    assert "确认创建投诉" in issue_response.json()["reply"]
    assert confirm_response.status_code == 200
    assert "已为用户创建投诉，编号 C-" in confirm_response.json()["reply"]
    assert "识别意图：confirm_create_complaint" in confirm_response.json()["steps"]
    assert "读取会话记忆：waiting_confirm" in confirm_response.json()["steps"]
    assert "整理投诉内容" in confirm_response.json()["steps"]
    assert "调用工具：create_complaint" in confirm_response.json()["steps"]
    assert "清空待确认动作" in confirm_response.json()["steps"]
    complaints = list_response.json()
    assert any(
        item["user_id"] == "pytest-confirm-logistics-complaint"
        and "物流号:L101" in item["content"]
        and "订单号:A101" in item["content"]
        for item in complaints
    )


def test_chat_endpoint_cancels_pending_complaint_when_llm_disabled():
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = False

    try:
        issue_response = client.post(
            "/chat",
            json={
                "user_id": "pytest-cancel-logistics-complaint",
                "message": "我的物流 L101 48小时了，怎么还没发货",
                "role": "agent",
            },
        )
        cancel_response = client.post(
            "/chat",
            json={
                "user_id": "pytest-cancel-logistics-complaint",
                "message": "取消创建投诉",
                "role": "agent",
            },
        )
        confirm_response = client.post(
            "/chat",
            json={
                "user_id": "pytest-cancel-logistics-complaint",
                "message": "确认创建投诉",
                "role": "agent",
            },
        )
    finally:
        settings.llm_enabled = original_llm_enabled

    assert issue_response.status_code == 200
    assert "确认创建投诉" in issue_response.json()["reply"]
    assert "保存待确认动作：waiting_confirm" in issue_response.json()["steps"]
    assert cancel_response.status_code == 200
    assert "已取消创建投诉" in cancel_response.json()["reply"]
    assert "识别意图：cancel_create_complaint" in cancel_response.json()["steps"]
    assert "读取会话记忆：waiting_confirm" in cancel_response.json()["steps"]
    assert "清空待确认动作" in cancel_response.json()["steps"]
    assert confirm_response.status_code == 200
    assert "当前没有待确认创建的投诉" in confirm_response.json()["reply"]


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
    steps = response.json()["steps"]
    assert response.status_code == 200
    assert "已同时查询订单状态和平台发货政策" in reply
    assert "订单 A101" in reply
    assert "当前状态" in reply
    assert "发货时效规则" in reply
    assert "建议您" in reply
    assert "参考来源" in reply
    assert "创建投诉" in reply
    assert "客服主管" in reply
    assert "执行模式：规则 Agent（本次未调用 LLM）" in steps
    assert "调用组合工具：handle_order_issue" in steps
    assert "内部调用：query_order" in steps
    assert "内部调用：search_knowledge" in steps


def test_pending_complaint_does_not_block_normal_order_query():
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = False
    user_id = "pytest-pending-then-query-order"

    try:
        issue_response = client.post(
            "/chat",
            json={
                "user_id": user_id,
                "message": "我的物流 L101 48小时了，怎么还没发货",
                "role": "agent",
            },
        )
        query_response = client.post(
            "/chat",
            json={
                "user_id": user_id,
                "message": "查订单 A101",
                "role": "agent",
            },
        )
    finally:
        settings.llm_enabled = original_llm_enabled

    assert issue_response.status_code == 200
    assert "保存待确认动作：waiting_confirm" in issue_response.json()["steps"]
    assert query_response.status_code == 200
    assert "订单 A101" in query_response.json()["reply"]
    assert "已准备好投诉内容" not in query_response.json()["reply"]


def test_pending_complaint_does_not_turn_greeting_into_complaint_confirmation():
    original_llm_enabled = settings.llm_enabled
    settings.llm_enabled = False
    user_id = "pytest-pending-then-greeting"

    try:
        issue_response = client.post(
            "/chat",
            json={
                "user_id": user_id,
                "message": "我的物流 L101 48小时了，怎么还没发货",
                "role": "agent",
            },
        )
        greeting_response = client.post(
            "/chat",
            json={
                "user_id": user_id,
                "message": "你好",
                "role": "agent",
            },
        )
    finally:
        settings.llm_enabled = original_llm_enabled

    assert issue_response.status_code == 200
    assert "保存待确认动作：waiting_confirm" in issue_response.json()["steps"]
    assert greeting_response.status_code == 200
    assert "已准备好投诉内容" not in greeting_response.json()["reply"]
    assert "我只能查询订单或物流" in greeting_response.json()["reply"]


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


def test_audit_logs_require_manager_role():
    token = login_token("agent1", "agent123")

    response = client.get(
        "/audit-logs",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "required role: manager"


def test_manager_can_view_audit_logs_and_stats():
    token = login_token("manager1", "manager123")

    logs_response = client.get(
        "/audit-logs",
        headers={"Authorization": f"Bearer {token}"},
    )
    stats_response = client.get(
        "/audit-logs/stats",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert logs_response.status_code == 200
    assert isinstance(logs_response.json(), list)
    assert stats_response.status_code == 200
    assert "total" in stats_response.json()
    assert "actions" in stats_response.json()


def test_login_success_and_failure_write_audit_logs():
    manager_token = login_token("manager1", "manager123")
    client.post(
        "/auth/login",
        json={"username": "agent1", "password": "wrong-password"},
    )

    response = client.get(
        "/audit-logs?limit=20",
        headers={"Authorization": f"Bearer {manager_token}"},
    )

    actions = [item["action"] for item in response.json()]
    assert response.status_code == 200
    assert "auth.login_success" in actions
    assert "auth.login_failed" in actions


def test_user_create_writes_audit_log():
    token = login_token("manager1", "manager123")
    username = "pytest_audit_user_create"

    client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": username,
            "password": "agent123",
            "display_name": "Audit User",
            "role": "agent",
        },
    )
    response = client.get(
        "/audit-logs?limit=20",
        headers={"Authorization": f"Bearer {token}"},
    )

    logs = response.json()
    assert response.status_code == 200
    assert any(
        item["action"] == "user.create" and item["target_id"] == username and item["success"] is True
        for item in logs
    )


def test_audit_logs_support_action_success_and_actor_filters():
    token = login_token("manager1", "manager123")
    username = "pytest_audit_filter_user"

    client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": username,
            "password": "agent123",
            "display_name": "Audit Filter User",
            "role": "agent",
        },
    )

    response = client.get(
        "/audit-logs?action=user.create&success=true&actor=manager1",
        headers={"Authorization": f"Bearer {token}"},
    )

    logs = response.json()
    assert response.status_code == 200
    assert logs
    assert all(item["action"] == "user.create" for item in logs)
    assert all(item["success"] is True for item in logs)
    assert all(item["actor_username"] == "manager1" for item in logs)


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


def test_knowledge_search_debug_returns_rag_explanations():
    response = client.get("/knowledge/search-debug?query=48%20%E7%89%A9%E6%B5%81")

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["query"] == "48 \u7269\u6d41"
    assert body["matches"]
    assert body["matches"][0]["score"] >= 3
    assert isinstance(body["matches"][0]["matched_keywords"], list)
    assert "match_reason" in body["matches"][0]
    assert "相关度分数" in body["matches"][0]["match_reason"]


def test_knowledge_search_debug_returns_empty_for_unrelated_query():
    response = client.get("/knowledge/search-debug?query=x")

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is False
    assert body["matches"] == []
    assert body["sources"] == []


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
