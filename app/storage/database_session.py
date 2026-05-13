from typing import Any, Dict, List

from app.storage.db import (
    clear_session_messages,
    fetch_session_messages,
    save_session_message,
)


class DatabaseSessionStore:
    """会话存储类，支持多用户状态跟踪（基于 SQLite 持久化）"""

    def append(self, user_id: str, message: Any) -> None:
        """保存一条消息到会话历史
        
        Args:
            user_id: 用户 ID
            message: 消息对象（通常是投诉流程字典）
        """
        # 简化处理：直接序列化为 JSON 字符串存储
        import json

        message_str = json.dumps(message, ensure_ascii=False, default=str)
        save_session_message(user_id, message_str, "system")

    def get(self, user_id: str) -> List[Any]:
        """获取用户的所有会话消息

        Args:
            user_id: 用户 ID

        Returns:
            消息列表，每条消息反序列化为原始对象
        """
        import json

        rows = fetch_session_messages(user_id)
        results = []
        for row in rows:
            try:
                obj = json.loads(row["message"])
                results.append(obj)
            except json.JSONDecodeError:
                # 如果反序列化失败，保留原始字符串
                results.append(row["message"])
        return results

    def clear(self, user_id: str) -> None:
        """清空用户的会话历史

        Args:
            user_id: 用户 ID
        """
        clear_session_messages(user_id)
