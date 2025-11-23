import logging
import re
from datetime import datetime

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from app.bot.admin_keyboards import get_main_keyboard
from app.bot.jobs import notify_users
from app.services.db_service import DbService
from app.services.redis_service import RedisService

logger = logging.getLogger(__name__)
admin_router = Router()


class NotificationDataRequest(StatesGroup):
    waiting_for_data = State()


@admin_router.message(Command("admin"))
async def cmd_admin(message: types.Message) -> None:
    await message.answer("Выберите действие:", reply_markup=get_main_keyboard())


@admin_router.callback_query(F.data == "notification")
async def handle_notification_button(callback: types.CallbackQuery, state: State) -> None:
    await state.set_state(NotificationDataRequest.waiting_for_data)
    await callback.message.answer(
        (
            "Введите текст уведомления и время рассылки в следующем формате:\n\n"
            "Текст # число:месяц:год:час:минута\n\nНапример: Какой-то текст # 01:12:2033:04:04\n\n"
            "Опционально можно прикрепить фото к этому же сообщению"
        ),
    )
    await callback.answer()


@admin_router.message(NotificationDataRequest.waiting_for_data)
async def create_notification_task(
    message: types.Message, state: State, scheduler: AsyncIOScheduler, db_service: DbService
) -> None:
    await state.clear()
    data = message.caption if message.caption else message.text
    spl = data.split("#")
    pattern = r"^(0[1-9]|[1-2][0-9]|3[01]):(0[1-9]|1[0-2]):\d{4}:(0[0-9]|1[0-9]|2[0-3]|[0-9]{2}):([0-5][0-9])$"
    if len(spl) != 2 or spl[0].strip() == "" or not re.match(pattern, spl[1].strip()):
        await message.answer("Неверный формат ввода, нажмите на кнопку снова", reply_markup=get_main_keyboard())
        return
    text, date = spl[0].strip(), spl[1].strip()
    spl_date = date.split(":")
    photo_id = message.photo[-1].file_id if message.photo else None
    user_ids = await db_service.get_users_ids()
    scheduler.add_job(
        notify_users,
        args=(text, user_ids, photo_id),
        misfire_grace_time=300,
        trigger=DateTrigger(
            run_date=datetime(
                year=int(spl_date[2]),
                month=int(spl_date[1]),
                day=int(spl_date[0]),
                hour=int(spl_date[3]),
                minute=int(spl_date[4]),
            )
        ),
    )

    logger.info(f"Scheduler jobs: {scheduler.get_jobs()}")
    await message.answer("Рассылка добавлена")


@admin_router.callback_query(F.data == "stats")
async def stats(callback: types.CallbackQuery, db_service: DbService, redis_service: RedisService) -> None:
    all_users_count = await db_service.get_users_count()
    daily_count = redis_service.get_daily_count()
    text = f"Cегодня {daily_count} новых пользователей\nВсего - {all_users_count}"
    await callback.message.answer(text)
    await callback.answer()


@admin_router.callback_query(F.data == "activity")
async def activity(callback: types.CallbackQuery, db_service: DbService) -> None:
    ans = await db_service.show_active_today_users()
    await callback.message.answer(text=ans)
    await callback.answer()
