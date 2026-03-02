import json
import logging
from typing import Any, Optional

from asyncpg import Record

from app.core.utils import sync_log_decorator
from app.repositories.redis_repo import RedisRepo

logger = logging.getLogger(__name__)


class RedisService:
    def __init__(self, repo: RedisRepo) -> None:
        self._repo = repo

    async def close_redis(self):
        await self._repo.close()

    async def set_user_msg(self, chat_id: int, msg_id: int) -> None:
        await self._repo.set(f"msg:{chat_id}", msg_id)

    async def get_user_msg(self, chat_id: int) -> Optional[int]:
        return await self._repo.get(f"msg:{chat_id}")

    async def set_user_data(self, user_id: int, data: dict[Any, Any]) -> None:
        logger.info(f"Setting data for {user_id=}")
        await self._repo.set(f"data:{user_id}", json.dumps(data))

    async def set_user_liked_disliked(self, user_id: int, data: list[Record], liked: bool = True) -> None:
        logger.info(f"Setting liked for {user_id=}")
        key = f"liked:{user_id}" if liked else f"disliked:{user_id}"
        serialized_data = [json.dumps(dict(r)) for r in data]
        if serialized_data:
            await self._repo.set_list(key, serialized_data)

    async def delete_key(self, user_id: int, liked: bool = True) -> None:
        key = f"liked:{user_id}" if liked else f"disliked:{user_id}"
        await self._repo.delete_key(key)

    async def get_liked_disliked(
        self, user_id: int, start_idx: int, end_idx: int, liked: bool = True
    ) -> list[dict[str, Any]]:
        key = f"liked:{user_id}" if liked else f"disliked:{user_id}"
        serialized_data = await self._repo.get_list(key, start_idx, end_idx)
        return [json.loads(d) for d in serialized_data]

    async def get_liked_disliked_count(self, user_id: int, liked: bool = True) -> int:
        key = f"liked:{user_id}" if liked else f"disliked:{user_id}"
        return len(await self._repo.get_list(key, 0, -1))

    async def get_user_data(self, user_id: int) -> dict[Any, Any]:
        data = await self._repo.get(f"data:{user_id}")
        return json.loads(data) if data is not None else {}

    async def set_user_data_params(self, user_id: int, params: dict[Any, Any]) -> None:
        data = await self.get_user_data(user_id)
        for k, v in params.items():
            data[k] = v
        await self.set_user_data(user_id, data)

    async def get_keys(self, pattern="*") -> list[Any]:
        return await self._repo.get_keys(pattern)

    @sync_log_decorator(logger)
    async def get_daily_count(self) -> int:
        res = await self._repo.get("daily_count")
        return int(res) if res else 0

    @sync_log_decorator(logger)
    async def set_daily_count(self, user_count: int) -> None:
        await self._repo.set("daily_count", user_count)
