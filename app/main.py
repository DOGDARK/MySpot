import asyncio
import logging
from math import atan2, cos, radians, sin, sqrt

from aiogram import F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.triggers.cron import CronTrigger

from app.bot_utils.keyboards import (
    get_back_to_filters_keyboard,
    get_back_to_main_keyboard,
    get_categories_keyboard,
    get_change_keyboard,
    get_filters_keyboard,
    get_main_keyboard,
    get_places_keyboard,
    get_reset_geolocation_keyboard,
    get_update_keyboard,
    get_view_places_keyboard,
    get_wishes_keyboard,
)
from app.bot_utils.msg_constants import AVAILABLE_FILTERS, MsgConstants
from app.bot_utils.utils import generate_place_text
from app.core.instances import bot, db_service, dp, redis_service, scheduler
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
        # scheduler.add_job(daily_report, CronTrigger(hour=0, minute=0), kwargs={"by_timer": True})
        scheduler.start()
        logger.info("Starting single-message bot with database support...")
        logger.info(f"Планировщик задач:, {scheduler.get_jobs()}")
        await dp.start_polling(bot)
    finally:
        logger.info("Error while starting, closing database...")
        await db_service.close_db()


if __name__ == "__main__":
    asyncio.run(main())