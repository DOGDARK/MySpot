import logging

from app.services.db_service import DbService
from app.services.redis_service import RedisService

logger = logging.getLogger(__name__)


class Coordinator:
    def __init__(self, db_service: DbService, redis_servise: RedisService) -> None:
        self._db_service = db_service
        self._redis_service = redis_servise

    async def save_user(
        self,
        user_id: int,
        categories: list = set(),
        wishes: list = set(),
        filters: list = None,
        latitude: float = None,
        longitude: float = None,
    ) -> None:
        await self._db_service.create_or_update_user(user_id, categories, wishes, filters, latitude, longitude)
        daily_count = self._redis_service.get_daily_count()
        self._redis_service.set_daily_count(daily_count + 1)
        logger.info(f"New user added {user_id=}, {daily_count + 1=}")
