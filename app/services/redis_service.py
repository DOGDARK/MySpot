import json
import logging
from typing import Any, Optional

from app.core.utils import sync_log_decorator
from app.repositories.redis_repo import RedisRepo

logger = logging.getLogger(__name__)


class RedisService:
    def __init__(self, repo: RedisRepo) -> None:
        self._repo = repo

    def close_redis(self):
        self._repo.close()

    @sync_log_decorator(logger)
    def set_user_msg(self, chat_id: int, msg_id: int) -> None:
        self._repo.set(f"msg:{chat_id}", msg_id)

    @sync_log_decorator(logger)
    def get_user_msg(self, chat_id: int) -> Optional[int]:
        return self._repo.get(f"msg:{chat_id}")

    @sync_log_decorator(logger)
    def set_user_data(self, user_id: int, data: dict[Any, Any]) -> None:
        self._repo.set(f"data:{user_id}", json.dumps(data))

    @sync_log_decorator(logger)
    def get_user_data(self, user_id: int) -> dict[Any, Any]:
        data = self._repo.get(f"data:{user_id}")
        return json.loads(data) if data is not None else {}

    @sync_log_decorator(logger)
    def set_user_data_params(self, user_id: int, params: dict[Any, Any]) -> None:
        data = self.get_user_data(user_id)
        for k, v in params.items():
            data[k] = v
        self.set_user_data(user_id, data)

    @sync_log_decorator(logger)
    def get_keys(self, pattern="*") -> list[Any]:
        return self._repo.get_keys(pattern)

    @sync_log_decorator(logger)
    def get_daily_count(self) -> int:
        res = self._repo.get("daily_count")
        return int(res) if res else 0

    @sync_log_decorator(logger)
    def set_daily_count(self, user_count: int) -> None:
        self._repo.set("daily_count", user_count)
