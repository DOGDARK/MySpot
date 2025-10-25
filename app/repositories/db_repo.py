import logging
from datetime import datetime
from typing import Any, Optional

import asyncpg

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
                    longitude DOUBLE PRECISION,
                    date_of_last_activity TIMESTAMP
                )
                """)

            # Создание таблицы логов (по одной строке на пользователя)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    user_id INTEGER PRIMARY KEY REFERENCES users(id),
                    activity_date TIMESTAMP,
                    viewed_places_count INTEGER DEFAULT 0,
                    has_geolocation BOOLEAN DEFAULT FALSE,
                    last_buttons TEXT,
                    total_activities INTEGER DEFAULT 1
                )
                """)
        logger.info("Created tables")

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
                longitude = $5, 
                date_of_last_activity = $6
                WHERE id = $7
                """,
                categories_str,
                wishes_str,
                filters_str,
                latitude,
                longitude,
                datetime.now(),
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
                longitude, 
                date_of_last_activity
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                user_id,
                categories_str,
                wishes_str,
                filters_str,
                latitude,
                longitude,
                datetime.now(),
            )

    async def get_viewed_places_count(self, user_id: int) -> int:
        try:
            if not await self.user_places_table_exists(user_id):
                return 0
            async with self._pool.acquire() as conn:
                return await conn.fetchval(f"""
                    SELECT COUNT(*) FROM user_{user_id} WHERE viewed = 1
                    """)
        except Exception as e:
            logger.error(f"Error while getting views places count {e}")
            return 0

    async def log_exists(self, user_id: int) -> bool:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT user_id FROM logs WHERE user_id = $1", user_id)
            return True if row else False

    async def user_places_table_exists(self, user_id: int) -> bool:
        async with self._pool.acquire() as conn:
            table_name = f"user_{int(user_id)}"
            row = await conn.fetchrow(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = $1
                """,
                table_name,
            )
            return row is not None

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
                datetime.now(),
                viewed_places_count,
                has_geolocation,
                last_buttons,
                total_activities,
                user_id,
            )

    async def user_count(self) -> None:
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
                    datetime.now(),
                    viewed_places_count,
                    has_geolocation,
                    last_buttons,
                ),
            )

    async def update_user_last_activity(self, user_id: int) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE users 
                SET date_of_last_activity = $1
                WHERE id = $2
                """,
                datetime.now(),
                user_id,
            )

    async def get_random_places(self) -> list[asyncpg.Record]:
        async with self._pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT name, address, description, categories_ya As categories, categories_1, categories_2,
                    photo, rating, latitude, longitude
                FROM places
                ORDER BY RANDOM()
                LIMIT 400
                """
            )

    async def get_places_data(self) -> list[asyncpg.Record]:
        async with self._pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT name, address, description, categories_ya, categories_1, 
                categories_2, photo, rating, latitude, longitude
                FROM places
                """
            )

    async def get_current_viewed_state_and_drop(self, user_id: int) -> dict[Any, Any]:
        async with self._pool.acquire() as conn:
            table_name = f"user_{int(user_id)}"
            rows = await conn.fetch(f"SELECT name, viewed FROM {table_name}")
            current_viewed_state = {row[0]: row[1] for row in rows}
            await conn.execute(f"DROP TABLE {table_name}")
            return current_viewed_state

    async def create_user_places_table(self, user_id: int) -> None:
        async with self._pool.acquire() as conn:
            table_name = f"user_{int(user_id)}"
            await conn.execute(
                f"""
                CREATE TABLE {table_name} (
                    id SERIAL PRIMARY KEY,
                    name TEXT,
                    address TEXT,
                    description TEXT,
                    categories TEXT,
                    photo TEXT,
                    rating TEXT,
                    latitude DOUBLE PRECISION,
                    longitude DOUBLE PRECISION,
                    viewed INTEGER DEFAULT 0
                    )
                """
            )

    async def save_user_places_data(
        self,
        user_id: int,
        name: str,
        address: str,
        description: str,
        categories: str,
        photo: str,
        rating: float,
        latitude: float,
        longitude: float,
        viewed: int,
    ):
        async with self._pool.acquire() as conn:
            table_name = f"user_{int(user_id)}"
            await conn.execute(
                f"""
                INSERT INTO {table_name}
                (name, address, description, categories, photo, 
                rating, latitude, longitude, viewed)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                name,
                address,
                description,
                categories,
                photo,
                rating,
                latitude,
                longitude,
                viewed,
            )

    async def get_ordered_user_places_data(self, user_id: int) -> list[asyncpg.Record]:
        logger.info(user_id)
        table_name = f"user_{int(user_id)}"
        async with self._pool.acquire() as conn:
            return await conn.fetch(
                f"""
                SELECT id, name, address, description, categories, 
                photo, rating, latitude, longitude
                FROM {table_name} 
                WHERE viewed = 0
                ORDER BY id ASC
                """
            )

    async def mark_place_as_viewed(self, user_id: int, place_name: str) -> None:
        table_name = f"user_{int(user_id)}"
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"""
                UPDATE {table_name} 
                SET viewed = 1 
                WHERE name = $1
                """,
                place_name,
            )

    async def reset_viewed(self, user_id: int) -> None:
        table_name = f"user_{int(user_id)}"
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"""
            UPDATE {table_name} 
            SET viewed = 0 
            WHERE viewed = 1
            """
            )

    async def reset_viewed_by_timer(self) -> None:
        """
        Сбрасывает значение столбца viewed до 0 во всех таблицах user_{user_id}.
        """
        async with self._pool.acquire() as conn:
            # Получаем всех пользователей
            rows = await conn.fetch("SELECT id FROM users")
            # Для каждого пользователя обновляем viewed
            for row in rows:
                table_name = f"user_{int(row['id'])}"
                try:
                    await conn.execute(f"UPDATE {table_name} SET viewed = 0")
                except Exception as e:
                    logger.error(f"Ошибка при обновлении {table_name}: {e}")
