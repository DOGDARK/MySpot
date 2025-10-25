import asyncio
import logging

from apscheduler.triggers.cron import CronTrigger

from app.bot.main_handlers import main_router
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
        logger.info("Starting single-message bot with database support...")
        logger.info(f"Планировщик задач:, {scheduler.get_jobs()}")
        dp.include_router(main_router)
        await dp.start_polling(bot)
    finally:
        logger.info("Error while starting, closing database...")
        await db_service.close_db()


if __name__ == "__main__":
    asyncio.run(main())
