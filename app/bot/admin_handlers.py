import re
from datetime import datetime

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from apscheduler.triggers.date import DateTrigger

from app.bot.admin_keyboards import get_main_keyboard, get_menu_keyboard
from app.bot.utils import notify_users
from app.core.instances import bot, scheduler

admin_router = Router()


class NotificationDataRequest(StatesGroup):
    waiting_for_data = State()


@admin_router.message(Command("admin"))
async def cmd_admin(message: types.Message):
    await message.answer("Выберите действие:", reply_markup=get_main_keyboard())


@admin_router.callback_query(F.data == "notification")
async def handle_notification_button(callback: types.CallbackQuery, state: State):
    await state.set_state(NotificationDataRequest.waiting_for_data)
    await callback.message.answer(
        (
            "Введите текст уведомления и время рассылки в следующем формате:\n\n"
            "Текст, число:месяц:год:час:минута\n\nНапример: Какой-то текст, 01:12:2033:04:05\n\n"
            "Опционально можно прикрепить фото к этому же сообщению"
        ),
    )
    await callback.answer()


@admin_router.message(NotificationDataRequest.waiting_for_data)
async def create_notification_task(message: types.Message, state: State):
    await state.clear()
    data = message.caption if message.caption else message.text
    spl = data.split(",")
    text, date = spl[0].strip(), spl[1].strip()
    pattern = r"^(0[1-9]|[1-2][0-9]|3[01]):(0[1-9]|1[0-2]):\d{4}:(0[0-9]|1[0-9]|2[0-3]|[0-9]{2}):([0-5][0-9])$"
    if len(spl) != 2 or not re.match(pattern, date):
        await message.answer("Неверный формат ввода, нажмите на кнопку снова", reply_markup=get_main_keyboard())
        return
    spl_date = date.split(":")
    photo_id = message.photo[-1].file_id if message.photo else None
    scheduler.add_job(
        notify_users,
        args=(bot, text, photo_id, get_menu_keyboard()),
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

    await message.answer("Рассылка добавлена")
