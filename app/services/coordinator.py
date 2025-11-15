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

    async def like_place(self, user_id: int):
        user_data = self._redis_service.get_user_data(user_id)
        current_index = user_data.get("current_place_index", 0)
        place = user_data.get("places", [])[current_index]
        place_name = place["name"]
        await self._db_service.mark_place_as_liked(user_id, place_name)

    async def dislike_place(self, user_id: int):
        user_data = self._redis_service.get_user_data(user_id)
        current_index = user_data.get("current_place_index", 0)
        place = user_data.get("places", [])[current_index]
        place_name = place["name"]
        await self._db_service.mark_place_as_disliked(user_id, place_name)

    async def show_liked_disliked(self, user_id: int, start_idx: int, end_idx: int, liked: bool = True) -> str:
        places = self._redis_service.get_liked_disliked(user_id, start_idx, end_idx, liked)

        text = ""
        if places:
            for idx in range(len(places)):
                text += f"{idx + 1}) {places[idx]['name']} {places[idx]['address']}\n"
        else:
            text = "Здесь пока пусто"
        return text

    async def move_to_redis_liked_disliked_places(self, user_id: int, liked: bool = True):
        if liked:
            places = await self._db_service.get_liked_places(user_id)
        else:
            places = await self._db_service.get_disliked_places(user_id)
        self._redis_service.set_user_liked_disliked(user_id, places, liked)

    async def delete_liked_disliked(self, user_id: int, place_name: str, liked: bool = True):
        try:
            print(self._redis_service.get_liked_disliked_count(user_id, liked))
            if self._redis_service.get_liked_disliked_count(user_id, liked) == 1:
                self._redis_service.delete_key(user_id, liked)
            return await self._db_service.delete_liked_disliked(user_id, place_name)
        except Exception as e:
            logger.error(f"Error deleting place from liked or disliked: {e}")
