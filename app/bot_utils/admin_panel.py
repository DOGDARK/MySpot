from app.core.instances import dp, bot
from aiogram import types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup


class PasswordRequest(StatesGroup):
    waiting_for_passwrod = State()


@dp.message(Command("admin"))
async def cmd_start(message: types.Message, state: State):
    pass