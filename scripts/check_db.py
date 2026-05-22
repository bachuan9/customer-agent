#!/usr/bin/env python
"""
检查 SQLite 数据库内容（无外部依赖）

阅读顺序：
1. 定位数据库文件
2. 检查数据库文件是否存在
3. 连接 SQLite
4. 查看有哪些表
5. 查看投诉表和会话表的最新数据
6. 额外验证订单/物流数据层函数
"""
import sqlite3
import os

db_path = "data/complaints.db"

print("=" * 70)
print("SQLite 数据库检查")
print("=" * 70)

# 第一步：检查数据库文件是否存在。
# 如果这个文件都不存在，说明后端可能还没启动过，或者数据库路径不对。
if not os.path.exists(db_path):
    print(f"\n✗ 数据库文件不存在: {db_path}")
    print("请确认后端已启动")
    exit(1)

print(f"\n✓ 数据库文件存在: {db_path}")
print(f"  大小: {os.path.getsize(db_path)} 字节")

# 第二步：连接数据库并读取表结构、投诉数据、会话数据。
try:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 列表所有表
    print("\n[表结构]")
    tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    for table in tables:
        print(f"  - {table[0]}")
    
    # 查询投诉表
    print("\n[投诉表 (complaints)]")
    complaints = cursor.execute("SELECT COUNT(*) FROM complaints").fetchone()
    count = complaints[0]
    print(f"  记录数: {count}")
    
    if count > 0:
        print("  最新 5 条:")
        rows = cursor.execute(
            "SELECT id, user_id, content, created_at FROM complaints ORDER BY id DESC LIMIT 5"
        ).fetchall()
        for i, row in enumerate(rows, 1):
            print(f"    {i}. [C-{row[0]:04d}] user={row[1]}, content={row[2][:50]}..., time={row[3]}")
    
    # 查询会话表
    print("\n[会话表 (session_messages)]")
    sessions = cursor.execute("SELECT COUNT(*) FROM session_messages").fetchone()
    count = sessions[0]
    print(f"  记录数: {count}")
    
    if count > 0:
        print("  最新 3 条:")
        rows = cursor.execute(
            "SELECT id, user_id, sender, message, created_at FROM session_messages ORDER BY id DESC LIMIT 3"
        ).fetchall()
        for i, row in enumerate(rows, 1):
            msg_preview = row[3][:40]
            print(f"    {i}. user={row[1]}, sender={row[2]}, msg={msg_preview}..., time={row[4]}")
    
    conn.close()
    
    print("\n" + "=" * 70)
    print("✓ 数据库连接成功，数据持久化正常")
    print("=" * 70)

except Exception as e:
    print(f"\n✗ 数据库错误: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# 第三步：直接调用 db.py 里的订单/物流函数，验证数据层函数是否可用。
from app.storage.db import (
    insert_order,
    get_order_status,
    update_order_status,
    insert_logistics,
    get_logistics_status,
    update_logistics_status,
)

insert_order("A100", "u001")
print(get_order_status("A100"))

update_order_status("A100", "shipped")
print(get_order_status("A100"))

insert_logistics("L100", "A100")
print(get_logistics_status("L100"))

update_logistics_status("L100", "in_transit")
print(get_logistics_status("L100"))
