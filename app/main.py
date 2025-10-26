import asyncio
import logging

import pytz
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from redis import Redis

from app.bot.admin_handlers import admin_router
from app.bot.base_handlers import base_router
from app.core.settings import Settings
from app.repositories.db_repo import DbRepo
from app.repositories.redis_repo import RedisRepo
from app.services.db_service import DbService
from app.services.redis_service import RedisService

logger = logging.getLogger(__name__)

# Инициализация
bot = Bot(token=Settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

scheduler = AsyncIOScheduler(timezone=pytz.timezone("Europe/Moscow"))

db_repo = DbRepo()
db_service = DbService(db_repo)

redis_repo = RedisRepo(Redis(Settings.REDIS_HOST, Settings.REDIS_PORT, decode_responses=True))
redis_service = RedisService(redis_repo)


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        await db_service.init_db(
            Settings.POSTGRES_USER,
            Settings.POSTGRES_PASSWORD,
            Settings.POSTGRES_DB,
            Settings.POSTGRES_HOST,
            Settings.POSTGRES_PORT,
        )

        await db_service.create_tables()

        routers = [base_router, admin_router]
        for router in routers:
            dp.include_router(router)

        dp["scheduler"] = scheduler
        dp["db_service"] = db_service
        dp["redis_service"] = redis_service

        commands = [
            BotCommand(command="help", description="Помощь"),
            BotCommand(command="admin", description="Панель администратора"),
        ]
        await bot.set_my_commands(commands)

        scheduler.add_job(
            db_service.reset_viewed_by_timer,
            CronTrigger(hour=4, minute=0),
            misfire_grace_time=300,
        )

        #scheduler.add (create_stats, args(db_service, redis_service, bot))

        scheduler.start()
        logger.info(f"Scheduler jobs: {scheduler.get_jobs()}")

        await dp.start_polling(bot)

    finally:
        await db_service.close_db()
        redis_service.close_redis()


if __name__ == "__main__":
    asyncio.run(main())
