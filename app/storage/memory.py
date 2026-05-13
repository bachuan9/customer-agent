from typing import Any, Dict, List


class MemoryStore:
    def __init__(self) -> None:
        self._data: Dict[str, List[Any]] = {}

    def append(self, user_id: str, message: str) -> None:
        self._data.setdefault(user_id, []).append(message)

    def get(self, user_id: str) -> List[Any]:
        return self._data.get(user_id, [])
