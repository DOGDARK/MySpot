import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import asyncpg
import pytz

logger = logging.getLogger(__name__)


class DbRepo:
    def __init__(self) -> None:
        self._pool: Optional[asyncpg.pool.Pool] = None

    async def init(self, user, password, database, host, port, min_size=10, max_size=30) -> None:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                user=user,
                password=password,
                database=database,
                host=host,
                port=port,
                min_size=min_size,
                max_size=max_size,
            )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def create_tables(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    categories TEXT,
                    wishes TEXT,
                    filters TEXT,
                    latitude DOUBLE PRECISION,
                    longitude DOUBLE PRECISION
                )
                """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    activity_date TIMESTAMPTZ,
                    viewed_places_count INTEGER DEFAULT 0,
                    has_geolocation BOOLEAN DEFAULT FALSE,
                    last_buttons TEXT,
                    total_activities INTEGER DEFAULT 1
                )
                """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users_places (
                    user_id BIGINT,
                    place_id INTEGER,   
                    PRIMARY KEY (user_id, place_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (place_id) REFERENCES places(id) ON DELETE CASCADE,
                    viewed BOOLEAN DEFAULT FALSE,
                    reset_viewed_time TIMESTAMPTZ 
                );
                """)

    async def get_user_stats(self, user_id: int) -> asyncpg.Record:
        """
        Получает статистику пользователя из таблицы logs
        """
        async with self._pool.acquire() as conn:
            try:
                return await conn.fetchrow(
                    """
                SELECT activity_date, viewed_places_count, has_geolocation, 
                last_buttons, total_activities
                FROM logs WHERE user_id = $1
                """,
                    user_id,
                )
            except Exception as e:
                logger.error(f"Error while getting user stats: {e}")
                return []

    # Получаем категории и пожелания места из базы данных
    async def get_categories_and_wishes(self, name: str, address: str) -> asyncpg.Record:
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT categories_1, categories_2, website FROM places 
                WHERE name = $1 AND address = $2
                """,
                name,
                address,
            )

    async def get_user(self, user_id: int) -> Optional[asyncpg.Record]:
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM users WHERE id = $1",
                user_id,
            )

    async def get_users_ids(self) -> list[asyncpg.Record]:
        async with self._pool.acquire() as conn:
            return await conn.fetch("SELECT id FROM users")

    async def update_user(
        self,
        user_id: int,
        categories_str: str,
        wishes_str: str,
        filters_str: str,
        latitude: float = None,
        longitude: float = None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE users 
                SET categories = $1, 
                wishes = $2, 
                filters = $3, 
                latitude = $4, 
                longitude = $5 
                WHERE id = $6
                """,
                categories_str,
                wishes_str,
                filters_str,
                latitude,
                longitude,
                user_id,
            )

    async def create_user(
        self,
        user_id: int,
        categories_str: str,
        wishes_str: str,
        filters_str: str,
        latitude: float = None,
        longitude: float = None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO users (
                id, 
                categories, 
                wishes, 
                filters, 
                latitude, 
                longitude
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                user_id,
                categories_str,
                wishes_str,
                filters_str,
                latitude,
                longitude,
            )

    async def get_viewed_places_count(self, user_id: int) -> int:
        try:
            async with self._pool.acquire() as conn:
                return await conn.fetchval(
                    """
                    SELECT COUNT(*) 
                    FROM users_places  
                    WHERE viewed = TRUE AND user_id = $1
                    """,
                    user_id,
                )
        except Exception as e:
            logger.error(f"Error while getting views places count {e}")
            return 0

    async def log_exists(self, user_id: int) -> bool:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT user_id FROM logs WHERE user_id = $1", user_id)
            return True if row else False

    async def user_places_relations_exists(self, user_id: int) -> None:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM users_places WHERE user_id = $1", user_id)
            return rows != []

    async def get_last_buttons(self, user_id: int) -> asyncpg.Record:
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT last_buttons, total_activities FROM logs WHERE user_id = $1",
                user_id,
            )

    async def update_logs(
        self,
        user_id: int,
        viewed_places_count: int,
        has_geolocation: bool,
        last_buttons: str,
        total_activities: int,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE logs 
                SET activity_date = $1, 
                    viewed_places_count = $2, 
                    has_geolocation = $3, 
                    last_buttons = $4,
                    total_activities = $5
                WHERE user_id = $6
                """,
                datetime.now(pytz.utc),
                viewed_places_count,
                has_geolocation,
                last_buttons,
                total_activities,
                user_id,
            )

    async def get_users_count(self) -> int:
        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                """
                SELECT COUNT(*) FROM users
                """
            )

    async def create_user_log(
        self,
        user_id: int,
        viewed_places_count: int,
        has_geolocation: bool,
        last_buttons: str,
    ) -> None:
        async with self._pool.acquire() as conn:
            (
                await conn.execute(
                    """
                INSERT INTO logs (
                user_id, 
                activity_date, 
                viewed_places_count, 
                has_geolocation, 
                last_buttons, 
                total_activities
                )
                VALUES ($1, $2, $3, $4, $5, 1)
                """,
                    user_id,
                    datetime.now(pytz.utc),
                    viewed_places_count,
                    has_geolocation,
                    last_buttons,
                ),
            )

    async def get_random_places(self) -> list[asyncpg.Record]:
        async with self._pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT id, name, address, description, categories_ya as categories, categories_1, 
                    categories_2, photo, rating, latitude, longitude
                FROM places
                ORDER BY RANDOM()
                LIMIT 400
                """
            )

    async def get_places_data(self) -> list[asyncpg.Record]:
        async with self._pool.acquire() as conn:
            res = await conn.fetch(
                """
                SELECT id, name, address, description, categories_ya, categories_1, 
                categories_2, photo, rating, latitude, longitude
                FROM places
                """
            )
            return res

    async def get_current_viewed_state_and_del(self, user_id: int) -> dict[Any, Any]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT places.name, up.viewed
                FROM users_places AS up
                LEFT JOIN places ON up.place_id = places.id
                WHERE up.user_id = $1
                """,
                user_id,
            )
            current_viewed_state = {row[0]: row[1] for row in rows}

            await conn.execute(
                """
                UPDATE users_places 
                SET viewed = FALSE 
                WHERE user_id = $1 AND CURRENT_TIMESTAMP >= reset_viewed_time 
                """,
                user_id,
            )
            await conn.execute(
                """
                DELETE FROM users_places
                WHERE user_id = $1 AND viewed = FALSE
                """,
                user_id,
            )
            return current_viewed_state

    async def save_user_places_relation(
        self,
        user_id: int,
        place_id: int,
        viewed: int,
    ):
        async with self._pool.acquire() as conn:
            reset_viewed_time = datetime.now(pytz.utc) + timedelta(weeks=1)
            await conn.execute(
                """
                INSERT INTO users_places(user_id, place_id, viewed, reset_viewed_time)
                VALUES ($1, $2, $3, $4)
                """,
                user_id,
                place_id,
                viewed,
                reset_viewed_time,
            )

    async def get_user_places_data(self, user_id: int) -> list[asyncpg.Record]:
        async with self._pool.acquire() as conn:
            return await conn.fetch(
                """
                WITH up AS (
                SELECT
                *,
                ROW_NUMBER() OVER () AS rn
                FROM users_places
                WHERE user_id = $1 AND viewed = FALSE
            )
                SELECT
                    p.id,
                    p.name,
                    p.address,
                    p.description,
                    p.categories_ya AS categories,
                    p.photo,
                    p.rating,
                    p.latitude,
                    p.longitude
                FROM up
                JOIN places AS p ON p.id = up.place_id
                ORDER BY up.rn;
                """,
                user_id,
            )

    async def mark_place_as_viewed(self, user_id: int, place_name: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE users_places AS up
                SET viewed = TRUE
                FROM places
                WHERE up.place_id = places.id
                AND places.name = $1
                AND up.user_id = $2
                """,
                place_name,
                user_id,
            )

    async def reset_viewed(self, user_id: int) -> None:  # Не используется
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE users_places 
                SET viewed = FALSE 
                WHERE user_id = $1
                """,
                user_id,
            )

    async def reset_viewed_by_timer(self) -> None:  # не используется
        """
        Меняет значение столбца viewed на False во всех связях пользователей с местами.
        """
        async with self._pool.acquire() as conn:
            await conn.execute("UPDATE users_places SET viewed = FALSE")

    async def get_active_today_users(self) -> list[asyncpg.Record]:
        async with self._pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT user_id, activity_date
                FROM logs
                WHERE activity_date AT TIME ZONE 'Europe/Moscow' >= CURRENT_DATE
                AND activity_date AT TIME ZONE 'Europe/Moscow' < CURRENT_DATE + INTERVAL '1 day'
                ORDER BY activity_date ASC
                """
            )

    async def delete_user(self, user_id: int) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM users WHERE id = $1", user_id)

    async def delete_place(self, place_id: int) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM places WHERE id = $1", place_id)
