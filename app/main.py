import asyncio
import logging

from aiogram.types import BotCommand
from apscheduler.triggers.cron import CronTrigger

from app.bot.admin_handlers import admin_router
from app.bot.base_handlers import base_router
from app.core.instances import bot, db_service, dp, scheduler
from app.core.settings import Settings

logger = logging.getLogger(__name__)


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

        scheduler.add_job(db_service.reset_viewed_by_timer, CronTrigger(hour=4, minute=0))
        scheduler.start()
        logger.info(f"Scheduler jobs: {scheduler.get_jobs()}")

        routers = [base_router, admin_router]
        for router in routers:
            dp.include_router(router)

        commands = [
            BotCommand(command="help", description="Помощь"),
            BotCommand(command="admin", description="Панель администратора"),
        ]
        await bot.set_my_commands(commands)

        await dp.start_polling(bot)

    finally:
        await db_service.close_db()


if __name__ == "__main__":
    asyncio.run(main())
