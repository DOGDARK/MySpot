import logging
from typing import Any, Optional

from redis import Redis

logger = logging.getLogger(__name__)


class RedisRepo:
    def __init__(self, redis: Redis):
        self._r = redis

    def close(self) -> None:
        self._r.close()

    def set(self, key: Any, val: Any) -> None:
        self._r.set(key, val)

    def get(self, key: Any) -> Optional[Any]:
        return self._r.get(key)

    def get_keys(self, pattern: str = "*") -> list[Any]:
        return self._r.keys(pattern)
