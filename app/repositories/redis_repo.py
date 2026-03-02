import logging
from typing import Any, Optional

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class RedisRepo:
    def __init__(self, redis: Redis):
        self._r = redis

    async def close(self) -> None:
        await self._r.close()

    async def set(self, key: Any, val: Any) -> None:
        await self._r.set(key, val)

    async def get(self, key: Any) -> Optional[Any]:
        return await self._r.get(key)

    async def get_keys(self, pattern: str = "*") -> list[Any]:
        return await self._r.keys(pattern)

    async def set_list(self, key: Any, val: list[Any]) -> None:
        await self._r.delete(key)
        await self._r.rpush(key, *val)

    async def delete_key(self, key: Any) -> None:
        await self._r.delete(key)

    async def get_list(self, key: Any, start_idx: int, end_idx: int) -> list[Any]:
        return await self._r.lrange(key, start_idx, end_idx)
