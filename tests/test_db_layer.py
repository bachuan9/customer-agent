import pytest

from app.storage.db import (
    fetch_tool_call_stats,
    get_order_by_no,
    get_order_status,
    insert_order,
    insert_tool_call_log,
    update_order_status,
)


def test_insert_and_get_order_by_no():
    order = insert_order("A202", "u202", "pending")

    saved_order = get_order_by_no(order["order_no"])

    assert saved_order["order_no"] == "A202"
    assert saved_order["user_id"] == "u202"
    assert saved_order["status"] == "pending"


def test_insert_order_rejects_duplicate_order_no():
    insert_order("A303", "u303", "pending")

    with pytest.raises(Exception):
        insert_order("A303", "u303", "pending")


def test_update_order_status_changes_existing_order():
    updated = update_order_status("A101", "delivered")

    assert updated is True
    assert get_order_status("A101") == "delivered"


def test_update_order_status_rejects_invalid_status():
    updated = update_order_status("A101", "not_a_status")

    assert updated is False
    assert get_order_status("A101") == "shipped"


def test_tool_call_stats_counts_sources_and_errors():
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

    stats = fetch_tool_call_stats()

    assert stats["total"] == 2
    assert stats["success"] == 1
    assert stats["failed"] == 1
    assert {"source": "llm_agent", "count": 1} in stats["sources"]
    assert {"source": "rbac_denied", "count": 1} in stats["sources"]
    assert {"error": "permission_denied", "count": 1} in stats["errors"]
