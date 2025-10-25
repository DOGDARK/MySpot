from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💌 Сформировать рассылку", callback_data="notification"),
            ],
            [
                InlineKeyboardButton(text="🕛 Посмотреть дневную статистику", callback_data="stats"),
            ],
        ]
    )


def get_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu"),
            ]
        ]
    )
