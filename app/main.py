import asyncio
import logging
import time

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
from app.services.coordinator import Coordinator
from app.services.db_service import DbService
from app.services.redis_service import RedisService

logger = logging.getLogger(__name__)

# Инициализация
bot = Bot(token=Settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

scheduler = AsyncIOScheduler(timezone=pytz.timezone("Europe/Moscow"))

db_repo = DbRepo()
db_service = DbService(db_repo)

redis_repo = RedisRepo(
    Redis(Settings.REDIS_HOST, Settings.REDIS_PORT, password=Settings.REDIS_PASSWORD, decode_responses=True)
)
redis_service = RedisService(redis_repo)

coordinator = Coordinator(db_service, redis_service)


async def main():
    logging.Formatter.converter = time.localtime
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
        dp["coordinator"] = coordinator

        commands = [
            BotCommand(command="start", description="Перезапуск бота"),
            BotCommand(command="help", description="Помощь"),
        ]
        await bot.set_my_commands(commands)

        scheduler.add_job(
            redis_service.set_daily_count,
            CronTrigger(hour=0, minute=0),
            misfire_grace_time=300,
            args=(0,),
        )

        scheduler.start()
        logger.info(f"Scheduler jobs: {scheduler.get_jobs()}")

        await dp.start_polling(bot)

    finally:
        await db_service.close_db()
        redis_service.close_redis()


if __name__ == "__main__":
    asyncio.run(main())
