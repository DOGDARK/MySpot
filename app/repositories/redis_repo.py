import logging
from typing import Any, Optional

from redis import Redis

logger = logging.getLogger(__name__)


class RedisRepo:
    def __init__(self, redis: Redis):
        self._r = redis

    def set(self, key: Any, val: Any) -> None:
        self._r.set(key, val)
        logger.info(f"set {key=}")

    def get(self, key: Any) -> Optional[Any]:
        logger.info(f"get {key=}")
        return self._r.get(key)

    def get_keys(self, pattern: str = "*") -> list[Any]:
        logger.info(f"get keys {pattern=}")
        return self._r.keys(pattern)

    def close(self) -> None:
        self._r.close()
