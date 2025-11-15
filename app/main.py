import asyncio
import logging
import time

from aiogram.types import BotCommand
from apscheduler.triggers.cron import CronTrigger

from app.bot.admin_handlers import admin_router
from app.bot.base_handlers import base_router
from app.bot.jobs import reset_daily_count
from app.core.instances import bot, coordinator, db_service, dp, redis_service, scheduler
from app.core.settings import Settings

logger = logging.getLogger(__name__)


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
            reset_daily_count,
            CronTrigger(hour=0, minute=0),
            misfire_grace_time=300,
            id="daily_count_reset",
            replace_existing=True,
        )

        scheduler.start()
        logger.info(f"Scheduler jobs: {scheduler.get_jobs()}")

        await dp.start_polling(bot)

    finally:
        await db_service.close_db()
        redis_service.close_redis()


if __name__ == "__main__":
    asyncio.run(main())
