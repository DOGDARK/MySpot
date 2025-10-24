import json
import logging
from typing import Any, Optional

from app.repositories.redis_repo import RedisRepo

logger = logging.getLogger(__name__)


class RedisService:
    _instance = None

    def __init__(self, repo: RedisRepo) -> None:
        self._repo = repo

    def __new__(cls, repo=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._repo = repo
        return cls._instance

    def set_user_msg(self, chat_id: int, msg_id: int) -> None:
        self._repo.set(f"msg:{chat_id}", msg_id)

    def get_user_msg(self, chat_id: int) -> Optional[int]:
        return self._repo.get(f"msg:{chat_id}")

    def set_user_data(self, user_id: int, data: dict[Any, Any]) -> None:
        self._repo.set(f"data:{user_id}", json.dumps(data))

    def get_user_data(self, user_id: int) -> dict[Any, Any]:
        data = self._repo.get(f"data:{user_id}")
        return json.loads(data) if data is not None else {}

    def set_user_data_params(self, user_id: int, params: dict[Any, Any]) -> None:
        data = self.get_user_data(user_id)
        for k, v in params.items():
            data[k] = v
        self.set_user_data(user_id, data)

    def get_keys(self, pattern="*") -> list[Any]:
        return self._repo.get_keys(pattern)
