import os
import json
import hashlib
import secrets
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

# 1. 业务规则常量：限制订单、物流、投诉可以使用的状态和优先级。
ALLOWED_LOGISTICS_STATUSES = {"pending", "in_transit", "delivered"}
ALLOWED_COMPLAINT_STATUSES = {"pending", "processing", "resolved"}
ALLOWED_COMPLAINT_PRIORITIES = {"low", "medium", "high"}
ALLOWED_STATUS_TRANSITIONS = {
    "pending": {"pending", "processing", "resolved"},
    "processing": {"processing", "resolved"},
    "resolved": {"resolved"},
}
ALLOWED_ORDER_STATUSES = {"pending", "shipped", "delivered"}


# 2. 数据库连接：确定 SQLite 文件位置，并创建连接。
def get_db_path() -> str:
    configured_path = os.getenv("APP_DB_PATH")
    if configured_path:
        configured_dir = os.path.dirname(os.path.abspath(configured_path))
        if configured_dir:
            os.makedirs(configured_dir, exist_ok=True)
        return configured_path

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "complaints.db")

# 3. 订单表初始化：创建 orders 表。
def init_orders_table() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_no TEXT NOT NULL UNIQUE,
                user_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT DEFAULT NULL
            )
            """
        )
        conn.commit()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


# 4. 总初始化入口：启动时创建所有需要的表。
def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                priority TEXT NOT NULL DEFAULT 'medium',
                handler TEXT DEFAULT NULL,
                updated_at TEXT DEFAULT NULL,
                resolved_at TEXT DEFAULT NULL
            )
            """
        )
        conn.commit()
    init_session_table()
    migrate_complaints_table()
    init_complaint_notes_table()
    init_tool_call_logs_table()
    init_orders_table()
    init_logistics_table()
    init_knowledge_articles_table()
    init_users_table()
    ensure_default_users()



# 5. 投诉表迁移：给旧表补齐新增字段。
def migrate_complaints_table() -> None:
    """为投诉表添加新字段（如果还没有的话）"""
    with get_connection() as conn:
        # 获取表里已经有的列名
        cursor = conn.execute("PRAGMA table_info(complaints)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        
        # 如果没有 status 列，就添加
        if 'status' not in existing_columns:
            conn.execute("ALTER TABLE complaints ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'")
        
        # 如果没有 priority 列，就添加
        if 'priority' not in existing_columns:
            conn.execute("ALTER TABLE complaints ADD COLUMN priority TEXT NOT NULL DEFAULT 'medium'")
        
        # 你需要继续添加：handler、updated_at、resolved_at 这三个字段
        # 按照同样的模式，自己试试写下去
        if 'handler' not in existing_columns:
            conn.execute("ALTER TABLE complaints ADD COLUMN handler TEXT DEFAULT NULL")

        if 'updated_at' not in existing_columns:
            conn.execute("ALTER TABLE complaints ADD COLUMN updated_at TEXT DEFAULT NULL")

        if 'resolved_at' not in existing_columns:
            conn.execute("ALTER TABLE complaints ADD COLUMN resolved_at TEXT DEFAULT NULL")
        conn.commit()

# 6. 会话记忆表：保存 Agent 多轮对话上下文。
def init_session_table() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                message TEXT NOT NULL,
                sender TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


# 7. 用户表：保存登录账号、角色和教学版 token。
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def init_users_table() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL,
                token TEXT DEFAULT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT DEFAULT NULL
            )
            """
        )
        conn.commit()


def format_user(row: sqlite3.Row, include_token: bool = False) -> Dict[str, str]:
    user = {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "role": row["role"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if include_token:
        user["token"] = row["token"]
    return user


def get_user_by_username(username: str) -> Optional[Dict[str, str]]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, username, password_hash, display_name, role, token, created_at, updated_at
            FROM users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()

    if row is None:
        return None
    user = format_user(row, include_token=True)
    user["password_hash"] = row["password_hash"]
    return user


def get_user_by_token(token: str) -> Optional[Dict[str, str]]:
    if not token:
        return None

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, username, password_hash, display_name, role, token, created_at, updated_at
            FROM users
            WHERE token = ?
            """,
            (token,),
        ).fetchone()

    if row is None:
        return None
    return format_user(row, include_token=True)


def insert_user(username: str, password: str, display_name: str, role: str) -> Dict[str, str]:
    created_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO users (username, password_hash, display_name, role, token, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (username, hash_password(password), display_name, role, None, created_at, None),
        )
        conn.commit()
        user_id = cursor.lastrowid

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, username, password_hash, display_name, role, token, created_at, updated_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
    return format_user(row)


def ensure_default_users() -> None:
    defaults = [
        ("agent1", "agent123", "普通客服 Alice", "agent"),
        ("manager1", "manager123", "主管 Bob", "manager"),
    ]
    for username, password, display_name, role in defaults:
        if get_user_by_username(username) is None:
            insert_user(username, password, display_name, role)


def login_user(username: str, password: str) -> Optional[Dict[str, str]]:
    user = get_user_by_username(username)
    if user is None:
        return None
    if user["password_hash"] != hash_password(password):
        return None

    token = secrets.token_urlsafe(32)
    updated_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET token = ?, updated_at = ? WHERE username = ?",
            (token, updated_at, username),
        )
        conn.commit()

    logged_in_user = get_user_by_username(username)
    return {
        "token": token,
        "user": {
            "id": logged_in_user["id"],
            "username": logged_in_user["username"],
            "display_name": logged_in_user["display_name"],
            "role": logged_in_user["role"],
        },
    }


def logout_user_by_token(token: str) -> bool:
    if not token:
        return False

    updated_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE users SET token = NULL, updated_at = ? WHERE token = ?",
            (updated_at, token),
        )
        conn.commit()
        return cursor.rowcount > 0


def save_session_message(user_id: str, message: str, sender: str) -> None:
    created_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO session_messages (user_id, message, sender, created_at) VALUES (?, ?, ?, ?)",
            (user_id, message, sender, created_at),
        )
        conn.commit()


def fetch_session_messages(user_id: str) -> List[Dict[str, str]]:
    query = (
        "SELECT id, user_id, message, sender, created_at "
        "FROM session_messages WHERE user_id = ? ORDER BY id ASC"
    )
    with get_connection() as conn:
        rows = conn.execute(query, (user_id,)).fetchall()

    results = []
    for row in rows:
        results.append(
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "message": row["message"],
                "sender": row["sender"],
                "created_at": row["created_at"],
            }
        )
    return results


def clear_session_messages(user_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM session_messages WHERE user_id = ?", (user_id,))
        conn.commit()


def init_tool_call_logs_table() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tool_call_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL DEFAULT 'unknown',
                tool_name TEXT NOT NULL,
                arguments TEXT NOT NULL,
                result TEXT NOT NULL,
                success INTEGER NOT NULL,
                error TEXT DEFAULT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        cursor = conn.execute("PRAGMA table_info(tool_call_logs)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        if "source" not in existing_columns:
            conn.execute("ALTER TABLE tool_call_logs ADD COLUMN source TEXT NOT NULL DEFAULT 'unknown'")
        conn.commit()


def insert_tool_call_log(
    tool_name: str,
    arguments: Dict,
    result: Dict,
    success: bool,
    error: Optional[str] = None,
    source: str = "rule_agent",
) -> None:
    created_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO tool_call_logs (source, tool_name, arguments, result, success, error, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source,
                tool_name,
                json.dumps(arguments, ensure_ascii=False),
                json.dumps(result, ensure_ascii=False),
                1 if success else 0,
                error,
                created_at,
            ),
        )
        conn.commit()


def fetch_tool_call_logs(
    limit: int = 20,
    source: Optional[str] = None,
    success: Optional[bool] = None,
) -> List[Dict[str, str]]:
    safe_limit = max(1, min(limit, 100))
    query = "SELECT id, source, tool_name, arguments, result, success, error, created_at FROM tool_call_logs"
    conditions = []
    params = []

    if source:
        conditions.append("source = ?")
        params.append(source)
    if success is not None:
        conditions.append("success = ?")
        params.append(1 if success else 0)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(safe_limit)

    with get_connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()

    return [
        {
            "id": row["id"],
            "source": row["source"],
            "tool_name": row["tool_name"],
            "arguments": json.loads(row["arguments"]),
            "result": json.loads(row["result"]),
            "success": bool(row["success"]),
            "error": row["error"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def fetch_tool_call_stats() -> Dict:
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) AS count FROM tool_call_logs").fetchone()["count"]
        success = conn.execute("SELECT COUNT(*) AS count FROM tool_call_logs WHERE success = 1").fetchone()["count"]
        failed = conn.execute("SELECT COUNT(*) AS count FROM tool_call_logs WHERE success = 0").fetchone()["count"]
        error_rows = conn.execute(
            """
            SELECT COALESCE(error, 'unknown') AS error, COUNT(*) AS count
            FROM tool_call_logs
            WHERE success = 0
            GROUP BY COALESCE(error, 'unknown')
            ORDER BY count DESC
            """
        ).fetchall()
        source_rows = conn.execute(
            """
            SELECT COALESCE(source, 'unknown') AS source, COUNT(*) AS count
            FROM tool_call_logs
            GROUP BY COALESCE(source, 'unknown')
            ORDER BY count DESC
            """
        ).fetchall()

    failure_rate = round(failed / total, 4) if total else 0
    return {
        "total": total,
        "success": success,
        "failed": failed,
        "failure_rate": failure_rate,
        "errors": [
            {
                "error": row["error"],
                "count": row["count"],
            }
            for row in error_rows
        ],
        "sources": [
            {
                "source": row["source"],
                "count": row["count"],
            }
            for row in source_rows
        ],
    }


def init_complaint_notes_table() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS complaint_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                complaint_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                author TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


# 7. 知识库表：保存可以通过后台维护的客服政策和规则。
def init_knowledge_articles_table() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                tags TEXT DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT DEFAULT NULL
            )
            """
        )
        conn.commit()


def format_knowledge_article(row: sqlite3.Row) -> Dict[str, str]:
    return {
        "id": row["id"],
        "title": row["title"],
        "content": row["content"],
        "tags": row["tags"],
        "enabled": bool(row["enabled"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def fetch_knowledge_articles(
    include_disabled: bool = False,
    query_text: Optional[str] = None,
    tag: Optional[str] = None,
) -> List[Dict[str, str]]:
    sql = "SELECT id, title, content, tags, enabled, created_at, updated_at FROM knowledge_articles"
    conditions = []
    params = []
    if not include_disabled:
        conditions.append("enabled = ?")
        params.append(1)
    if query_text:
        keyword = f"%{query_text.strip()}%"
        conditions.append("(title LIKE ? OR content LIKE ?)")
        params.extend([keyword, keyword])
    if tag:
        conditions.append("tags LIKE ?")
        params.append(f"%{tag.strip()}%")
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY id DESC"

    with get_connection() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()

    return [format_knowledge_article(row) for row in rows]


def get_knowledge_article(article_id: int) -> Optional[Dict[str, str]]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, title, content, tags, enabled, created_at, updated_at
            FROM knowledge_articles
            WHERE id = ?
            """,
            (article_id,),
        ).fetchone()

    if row is None:
        return None
    return format_knowledge_article(row)


def insert_knowledge_article(
    title: str,
    content: str,
    tags: str = "",
    enabled: bool = True,
) -> Dict[str, str]:
    cleaned_title = title.strip()
    cleaned_content = content.strip()
    cleaned_tags = tags.strip()

    if not cleaned_title:
        raise ValueError("knowledge title is required")
    if not cleaned_content:
        raise ValueError("knowledge content is required")

    created_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO knowledge_articles (title, content, tags, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (cleaned_title, cleaned_content, cleaned_tags, 1 if enabled else 0, created_at, None),
        )
        conn.commit()
        article_id = cursor.lastrowid

    return get_knowledge_article(article_id)


def update_knowledge_article(
    article_id: int,
    *,
    title: Optional[str] = None,
    content: Optional[str] = None,
    tags: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> Optional[Dict[str, str]]:
    article = get_knowledge_article(article_id)
    if article is None:
        return None

    next_title = article["title"] if title is None else title.strip()
    next_content = article["content"] if content is None else content.strip()
    next_tags = article["tags"] if tags is None else tags.strip()
    next_enabled = article["enabled"] if enabled is None else enabled

    if not next_title:
        raise ValueError("knowledge title is required")
    if not next_content:
        raise ValueError("knowledge content is required")

    updated_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE knowledge_articles
            SET title = ?, content = ?, tags = ?, enabled = ?, updated_at = ?
            WHERE id = ?
            """,
            (next_title, next_content, next_tags, 1 if next_enabled else 0, updated_at, article_id),
        )
        conn.commit()

    return get_knowledge_article(article_id)


def delete_knowledge_article(article_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM knowledge_articles WHERE id = ?", (article_id,))
        conn.commit()
        return cursor.rowcount > 0


# 8. 投诉工单：创建、查询、筛选投诉记录。
def insert_complaint(user_id: str, content: str, status: str = "pending", priority: str = "medium") -> str:
    created_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO complaints (user_id, content, created_at, status, priority, handler, updated_at, resolved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, content, created_at, status, priority, None, None, None),
        )
        conn.commit()
        complaint_id = cursor.lastrowid
    return f"C-{complaint_id:04d}"


def fetch_complaints(
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    handler: Optional[str] = None,
) -> List[Dict[str, str]]:
    query = "SELECT id, user_id, content, created_at, status, priority, handler, updated_at, resolved_at FROM complaints"
    conditions = []
    params = []
    if user_id:
        conditions.append("user_id = ?")
        params.append(user_id)
    if status:
        conditions.append("status = ?")
        params.append(status)
    if priority:
        conditions.append("priority = ?")
        params.append(priority)
    if handler:
        conditions.append("handler = ?")
        params.append(handler)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY id ASC"

    with get_connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()

    results = []
    for row in rows:
        results.append({
            "id": f"C-{row['id']:04d}",
            "user_id": row["user_id"],
            "content": row["content"],
            "created_at": row["created_at"],
            "status": row["status"],
            "priority": row["priority"],
            "handler": row["handler"],
            "updated_at": row["updated_at"],
            "resolved_at": row["resolved_at"]
        })
    return results


def fetch_complaint_stats() -> Dict[str, int]:
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) AS count FROM complaints").fetchone()["count"]
        pending = conn.execute("SELECT COUNT(*) AS count FROM complaints WHERE status = ?", ("pending",)).fetchone()["count"]
        processing = conn.execute("SELECT COUNT(*) AS count FROM complaints WHERE status = ?", ("processing",)).fetchone()["count"]
        resolved = conn.execute("SELECT COUNT(*) AS count FROM complaints WHERE status = ?", ("resolved",)).fetchone()["count"]
        high_priority = conn.execute("SELECT COUNT(*) AS count FROM complaints WHERE priority = ?", ("high",)).fetchone()["count"]

    return {
        "total": total,
        "pending": pending,
        "processing": processing,
        "resolved": resolved,
        "high_priority": high_priority,
    }


# 9. 单条投诉查询：根据 C-xxxx 找到对应投诉。
def get_complaint_by_id(complaint_id: str) -> Optional[Dict[str, str]]:
    try:
        numeric_id = int(complaint_id[2:] if complaint_id.upper().startswith("C-") else complaint_id)
    except (TypeError, ValueError):
        return None

    query = "SELECT id, user_id, content, created_at, status, priority, handler, updated_at, resolved_at FROM complaints WHERE id = ?"
    with get_connection() as conn:
        row = conn.execute(query, (numeric_id,)).fetchone()

    if row is None:
        return None

    return {
        "id": f"C-{row['id']:04d}",
        "user_id": row["user_id"],
        "content": row["content"],
        "created_at": row["created_at"],
        "status": row["status"],
        "priority": row["priority"],
        "handler": row["handler"],
        "updated_at": row["updated_at"],
        "resolved_at": row["resolved_at"],
    }


# 10. 投诉更新：更新状态、优先级、处理人和时间字段。
def update_complaint(
    complaint_id: str,
    *,
    status: Optional[str] = None,
    handler: Optional[str] = None,
    priority: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    complaint = get_complaint_by_id(complaint_id)
    if complaint is None:
        return None

    current_status = complaint["status"]
    next_status = current_status if status is None else status
    if next_status not in ALLOWED_COMPLAINT_STATUSES:
        raise ValueError("invalid complaint status")
    if next_status not in ALLOWED_STATUS_TRANSITIONS[current_status]:
        raise ValueError("invalid complaint status transition")

    next_handler = complaint["handler"]
    if handler is not None:
        next_handler = handler.strip() or None

    next_priority = complaint["priority"]
    if priority is not None:
        next_priority = priority.strip().lower()
    if next_priority not in ALLOWED_COMPLAINT_PRIORITIES:
        raise ValueError("invalid complaint priority")

    resolved_at = complaint["resolved_at"]
    if next_status == "resolved" and current_status != "resolved":
        resolved_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    updated_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    numeric_id = int(complaint["id"][2:])

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE complaints
            SET status = ?, priority = ?, handler = ?, updated_at = ?, resolved_at = ?
            WHERE id = ?
            """,
            (next_status, next_priority, next_handler, updated_at, resolved_at, numeric_id),
        )
        conn.commit()

    return get_complaint_by_id(complaint_id)


# 11. 投诉备注：添加、查询、修改、删除 complaint_notes 子记录。
def insert_complaint_note(complaint_id: str, content: str, author: str = "客服") -> Optional[Dict[str, str]]:
    complaint = get_complaint_by_id(complaint_id)
    if complaint is None:
        return None

    cleaned_content = content.strip()
    if not cleaned_content:
        raise ValueError("complaint note content is required")

    cleaned_author = author.strip() or "客服"
    numeric_id = int(complaint["id"][2:])
    created_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO complaint_notes (complaint_id, content, author, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (numeric_id, cleaned_content, cleaned_author, created_at),
        )
        conn.commit()
        note_id = cursor.lastrowid

    return {
        "id": f"N-{note_id:04d}",
        "complaint_id": complaint["id"],
        "content": cleaned_content,
        "author": cleaned_author,
        "created_at": created_at,
    }


def fetch_complaint_notes(complaint_id: str) -> Optional[List[Dict[str, str]]]:
    complaint = get_complaint_by_id(complaint_id)
    if complaint is None:
        return None

    numeric_id = int(complaint["id"][2:])
    query = (
        "SELECT id, complaint_id, content, author, created_at "
        "FROM complaint_notes WHERE complaint_id = ? ORDER BY id ASC"
    )
    with get_connection() as conn:
        rows = conn.execute(query, (numeric_id,)).fetchall()

    return [
        {
            "id": f"N-{row['id']:04d}",
            "complaint_id": f"C-{row['complaint_id']:04d}",
            "content": row["content"],
            "author": row["author"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def get_complaint_note_by_id(note_id: str) -> Optional[Dict[str, str]]:
    try:
        numeric_id = int(note_id[2:] if note_id.upper().startswith("N-") else note_id)
    except (TypeError, ValueError):
        return None

    query = "SELECT id, complaint_id, content, author, created_at FROM complaint_notes WHERE id = ?"
    with get_connection() as conn:
        row = conn.execute(query, (numeric_id,)).fetchone()

    if row is None:
        return None

    return {
        "id": f"N-{row['id']:04d}",
        "complaint_id": f"C-{row['complaint_id']:04d}",
        "content": row["content"],
        "author": row["author"],
        "created_at": row["created_at"],
    }


def update_complaint_note(note_id: str, content: str) -> Optional[Dict[str, str]]:
    note = get_complaint_note_by_id(note_id)
    if note is None:
        return None

    cleaned_content = content.strip()
    if not cleaned_content:
        raise ValueError("complaint note content is required")

    numeric_id = int(note["id"][2:])
    with get_connection() as conn:
        conn.execute(
            "UPDATE complaint_notes SET content = ? WHERE id = ?",
            (cleaned_content, numeric_id),
        )
        conn.commit()

    return get_complaint_note_by_id(note_id)


def delete_complaint_note(note_id: str) -> bool:
    try:
        numeric_id = int(note_id[2:] if note_id.upper().startswith("N-") else note_id)
    except (TypeError, ValueError):
        return False

    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM complaint_notes WHERE id = ?", (numeric_id,))
        conn.commit()
        return cursor.rowcount > 0

# 12. 订单数据：创建、查询、列表、更新订单。
def insert_order(order_no: str, user_id: str, status: str = "pending") -> Dict[str, str]:
    created_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO orders (order_no, user_id, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (order_no, user_id, status, created_at, None),
        )
        conn.commit()
    return {
        "order_no": order_no,
        "user_id": user_id,
        "status": status,
        "created_at": created_at,
    }

def get_order_status(order_no: str) -> Optional[str]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT status FROM orders WHERE order_no = ?",
            (order_no,)
        ).fetchone()

    if row is None:
        return None
    return row["status"]


def get_order_by_no(order_no: str) -> Optional[Dict[str, str]]:
    query = "SELECT order_no, user_id, status, created_at, updated_at FROM orders WHERE order_no = ?"
    with get_connection() as conn:
        row = conn.execute(query, (order_no,)).fetchone()

    if row is None:
        return None

    return {
        "order_no": row["order_no"],
        "user_id": row["user_id"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def fetch_orders() -> List[Dict[str, str]]:
    query = "SELECT order_no, user_id, status, created_at, updated_at FROM orders ORDER BY id ASC"
    with get_connection() as conn:
        rows = conn.execute(query).fetchall()

    results = []
    for row in rows:
        results.append(
            {
                "order_no": row["order_no"],
                "user_id": row["user_id"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    return results


def update_order_status(order_no: str, new_status: str) -> bool:
    if new_status not in ALLOWED_ORDER_STATUSES:
        return False

    updated_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE orders SET status = ?, updated_at = ? WHERE order_no = ?",
            (new_status, updated_at, order_no),
        )
        conn.commit()
        return cursor.rowcount > 0

# 13. 物流数据：创建、查询、列表、更新物流。
def init_logistics_table() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS logistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tracking_no TEXT NOT NULL UNIQUE,
                order_no TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT DEFAULT NULL
            )
            """
        )
        conn.commit()

def get_logistics_status(tracking_no: str) -> Optional[str]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT status FROM logistics WHERE tracking_no = ?",
            (tracking_no,)
        ).fetchone()

    if row is None:
        return None
    return row["status"]


def get_logistics_by_tracking_no(tracking_no: str) -> Optional[Dict[str, str]]:
    query = "SELECT tracking_no, order_no, status, created_at, updated_at FROM logistics WHERE tracking_no = ?"
    with get_connection() as conn:
        row = conn.execute(query, (tracking_no,)).fetchone()

    if row is None:
        return None

    return {
        "tracking_no": row["tracking_no"],
        "order_no": row["order_no"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def fetch_logistics() -> List[Dict[str, str]]:
    query = "SELECT tracking_no, order_no, status, created_at, updated_at FROM logistics ORDER BY id ASC"
    with get_connection() as conn:
        rows = conn.execute(query).fetchall()

    results = []
    for row in rows:
        results.append(
            {
                "tracking_no": row["tracking_no"],
                "order_no": row["order_no"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    return results


def insert_logistics(tracking_no: str, order_no: str, status: str = "pending") -> None:
    created_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO logistics (tracking_no, order_no, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (tracking_no, order_no, status, created_at, None),
        )
        conn.commit()

def update_logistics_status(tracking_no: str, new_status: str) -> bool:
    if new_status not in ALLOWED_LOGISTICS_STATUSES:
        return False

    updated_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE logistics SET status = ?, updated_at = ? WHERE tracking_no = ?",
            (new_status, updated_at, tracking_no),
        )
        conn.commit()
        return cursor.rowcount > 0

