from typing import Optional

import asyncpg


class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.pool.Pool] = None

    async def init(self, user, password, database, host, port, min_size=10, max_size=30) -> None:
        self.pool = await asyncpg.create_pool(
            user=user,
            password=password,
            database=database,
            host=host,
            port=port,
            min_size=min_size,
            max_size=max_size,
        )

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()
