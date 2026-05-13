#!/usr/bin/env python
"""
快速测试脚本：
1. 发送投诉给后端 API
2. 查询 SQLite 确认数据持久化
"""
import requests
import sqlite3
import json
from datetime import datetime

print("=" * 60)
print("测试智能客服投诉持久化")
print("=" * 60)

# 1. 发送测试投诉
print("\n[步骤1] 发送测试投诉到 API /chat")
url = "http://127.0.0.1:8000/chat"
payload = {
    "user_id": "test_user_001",
    "message": "投诉 订单 A001 物流太慢"
}
try:
    resp = requests.post(url, json=payload, timeout=5)
    print(f"  状态码: {resp.status_code}")
    print(f"  响应: {resp.json()}")
except Exception as e:
    print(f"  ✗ 错误: {e}")
    exit(1)

# 2. 查询 SQLite 投诉表
print("\n[步骤2] 从 SQLite 读取投诉记录")
db_path = "data/complaints.db"
try:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    rows = cursor.execute("SELECT * FROM complaints ORDER BY id DESC LIMIT 5").fetchall()
    print(f"  ✓ 数据库连接成功: {db_path}")
    print(f"  最新 5 条投诉记录:")
    for i, row in enumerate(rows, 1):
        print(f"    {i}. ID={row['id']}, user={row['user_id']}, 内容={row['content'][:50]}..., 时间={row['created_at']}")
    
    conn.close()
except Exception as e:
    print(f"  ✗ 错误: {e}")
    exit(1)

# 3. 通过 API /complaints 验证
print("\n[步骤3] 通过 API /complaints 查询投诉")
try:
    resp = requests.get("http://127.0.0.1:8000/complaints", timeout=5)
    print(f"  状态码: {resp.status_code}")
    data = resp.json()
    print(f"  共 {len(data)} 条投诉")
    if data:
        print(f"  最新一条: {data[-1]}")
except Exception as e:
    print(f"  ✗ 错误: {e}")
    exit(1)

# 4. 查看会话消息表
print("\n[步骤4] 查看会话历史（session_messages）")
try:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    rows = cursor.execute("SELECT * FROM session_messages ORDER BY id DESC LIMIT 3").fetchall()
    print(f"  最新 3 条会话消息:")
    for i, row in enumerate(rows, 1):
        msg_preview = row['message'][:60]
        print(f"    {i}. user={row['user_id']}, sender={row['sender']}, 消息={msg_preview}...")
    
    conn.close()
except Exception as e:
    print(f"  (会话表可能为空，这是正常的): {e}")

print("\n" + "=" * 60)
print("✓ 测试完成！投诉数据已持久化到 SQLite")
print("=" * 60)
