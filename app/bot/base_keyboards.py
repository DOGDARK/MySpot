from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.msgs_text import AVAILABLE_FILTERS, MsgsText
from app.services.coordinator import Coordinator
from app.services.db_service import DbService
from app.services.redis_service import RedisService


async def get_filters_keyboard(user_id: int, db_service: DbService, page: int = 0) -> InlineKeyboardMarkup:
    user_filters = await db_service.get_user_filters(user_id)
    buttons = []

    # Определяем, какие фильтры показывать на текущей странице
    items_per_page = 8
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    current_filters = AVAILABLE_FILTERS[start_idx:end_idx]

    # Создаем кнопки для фильтров (по 2 в ряд)
    for i in range(0, len(current_filters), 2):
        row = []
        for filter_name in current_filters[i : i + 2]:
            # Обрезаем длинные названия для лучшего отображения
            display_name = filter_name[:20] + "..." if len(filter_name) > 23 else filter_name
            emoji = "✅ " if filter_name in user_filters else ""
            # Используем индекс фильтра вместо полного названия
            filter_index = AVAILABLE_FILTERS.index(filter_name)
            row.append(
                InlineKeyboardButton(
                    text=f"{emoji}{display_name}",
                    callback_data=f"filter_{filter_index}_{page}",  # Используем индекс и страницу
                )
            )
        buttons.append(row)

    # Кнопки навигации
    nav_buttons = []
    total_pages = (len(AVAILABLE_FILTERS) + items_per_page - 1) // items_per_page

    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"filters_page_{page - 1}"))

    # Добавляем индикатор страницы
    nav_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="current_page"))

    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"filters_page_{page + 1}"))

    if nav_buttons:
        buttons.append(nav_buttons)

    # Кнопки действий
    buttons.append([InlineKeyboardButton(text="🔍 Поиск фильтра", callback_data="search_filter")])
    buttons.append([InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_filters")])
    buttons.append([InlineKeyboardButton(text="🗑️ Сбросить все фильтры", callback_data="reset_all_filters")])
    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data="main_menu")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def get_guide_keyboard(page: int = 0):
    total_pages = 2
    buttons = []

    nav_row = []

    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"guide_page_{page - 1}"))

    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="➡️ Вперёд", callback_data=f"guide_page_{page + 1}"))

    if nav_row:
        buttons.append(nav_row)

    if page == total_pages:
        buttons.append([InlineKeyboardButton(text="Завершить", callback_data="main_menu")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def get_like_dislike_keyboard(
    coordinator: Coordinator, redis_service: RedisService, user_id: int, page: int = 0, like: bool = True
) -> InlineKeyboardMarkup:
    if like:
        buttons = []

        items_per_page = 8
        start_idx = page * items_per_page
        end_idx = start_idx + items_per_page - 1
        liked_places = await redis_service.get_liked_disliked(user_id, start_idx, end_idx)

        buttons = []
        for i in range(0, len(liked_places), 2):
            row = []
            for j, place in enumerate(liked_places[i : i + 2], start=i):
                row.append(
                    InlineKeyboardButton(
                        text=str(j % 8 + 1),
                        callback_data=f"liked_{j}_{page}",
                    )
                )
            buttons.append(row)

        total_liked = await redis_service.get_liked_disliked_count(user_id)
        total_pages = (total_liked + items_per_page - 1) // items_per_page
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"like_page_{page - 1}"))
        nav_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="current_page"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"like_page_{page + 1}"))
        if nav_buttons:
            buttons.append(nav_buttons)
        buttons.append([InlineKeyboardButton(text="Скрытые 🚫", callback_data="show_dislike")])
    else:
        buttons = []

        items_per_page = 8
        start_idx = page * items_per_page
        end_idx = start_idx + items_per_page - 1
        disliked_places = await redis_service.get_liked_disliked(user_id, start_idx, end_idx, False)

        for i in range(0, len(disliked_places), 2):
            row = []
            for place in disliked_places[i : i + 2]:
                place_index = disliked_places.index(place)
                row.append(
                    InlineKeyboardButton(
                        text=f"{place_index % 8 + 1}",
                        callback_data=f"disliked_{place_index}_{page}",
                    )
                )
            buttons.append(row)

        total_disliked = await redis_service.get_liked_disliked_count(user_id, False)
        total_pages = (total_disliked + items_per_page - 1) // items_per_page
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"dislike_page_{page - 1}"))
        nav_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="current_page"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"dislike_page_{page + 1}"))
        if nav_buttons:
            buttons.append(nav_buttons)
        buttons.append([InlineKeyboardButton(text="❤️ Избранное", callback_data="show_like")])

    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data="main_menu")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def liked_keyboard(page: int, place_index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Убрать", callback_data=f"delete_from_liked_{8 * page + place_index}"),
                InlineKeyboardButton(text="Назад", callback_data=f"like_page_{page}"),
            ]
        ]
    )


def disliked_keyboard(page: int, place_index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Убрать", callback_data=f"delete_from_disliked_{8 * page + place_index}"),
                InlineKeyboardButton(text="Назад", callback_data=f"dislike_page_{page}"),
            ]
        ]
    )


def get_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📍 Просмотр мест", callback_data="view_places_main"),
                InlineKeyboardButton(text="❤️ Избранное", callback_data="show_like"),
            ],
            [
                InlineKeyboardButton(text="⚙️ Фильтры", callback_data="show_filters_main"),
                InlineKeyboardButton(text="📂 Категории", callback_data="show_categories_main"),
            ],
            [
                InlineKeyboardButton(text="🗺️ Геолокация", callback_data="show_geolocation_main"),
                InlineKeyboardButton(text="❓ Помощь", callback_data="show_help_main"),
            ],
        ]
    )


def get_reset_geolocation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗺️ Указать геолокацию",
                    callback_data="request_location",
                )
            ],
            [InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")],
        ]
    )


async def get_categories_keyboard(user_id: int, redis_service: RedisService) -> InlineKeyboardMarkup:
    selected_categories = (await redis_service.get_user_data(user_id)).get("selected_categories", [])
    buttons = []

    categories = [(category_type, category_type) for category_type in MsgsText.CATEGORIES_TYPES.value]

    for i in range(0, len(categories), 2):
        row = []
        for text, callback_data in categories[i : i + 2]:
            emoji = "✅ " if callback_data in selected_categories else ""
            row.append(InlineKeyboardButton(text=f"{emoji}{text}", callback_data=callback_data))
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="Подтвердить", callback_data="confirm_categories")])
    buttons.append([InlineKeyboardButton(text="🗑️ Сбросить все категории", callback_data="reset_all_categories")])
    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def get_wishes_keyboard(user_id: int, redis_service: RedisService) -> InlineKeyboardMarkup:
    selected_wishes = (await redis_service.get_user_data(user_id)).get("selected_wishes", [])
    buttons = []

    wishes = [(wish_type, wish_type) for wish_type in MsgsText.WISHES_TYPES.value]

    for i in range(0, len(wishes), 2):
        row = []
        for text, callback_data in wishes[i : i + 2]:
            emoji = "✅ " if callback_data in selected_wishes else ""
            row.append(InlineKeyboardButton(text=f"{emoji}{text}", callback_data=callback_data))
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="Подтвердить", callback_data="confirm_wishes")])
    buttons.append([InlineKeyboardButton(text="🗑️ Сбросить все пожелания", callback_data="reset_all_wishes")])
    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_places_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="place_prev"),
                InlineKeyboardButton(text="Вперёд ➡️", callback_data="place_next"),
            ],
            [
                InlineKeyboardButton(text="Нравится ❤️", callback_data="like_place"),
                InlineKeyboardButton(text="Не нравится 🚫", callback_data="dislike_place"),
            ],
            [
                InlineKeyboardButton(text="Проблема с местом?", callback_data="place_bad"),
                InlineKeyboardButton(text="Главное меню ↩️", callback_data="main_menu"),
            ],
        ]
    )


def get_back_to_main_keyboard(help: bool = False) -> InlineKeyboardMarkup:
    inline_keyboard = [[InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")]]
    if help:
        inline_keyboard[0].append(InlineKeyboardButton(text="🔎 Обучалка", callback_data="guide_page_0"))
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def get_update_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Сбросить историю просмотров",
                    callback_data="reset_viewed",
                )
            ],
            [InlineKeyboardButton(text="⚙️ Изменить настройки", callback_data="main_menu")],
            [
                InlineKeyboardButton(
                    text="🗺️ Обновить геолокацию",
                    callback_data="show_geolocation_main",
                )
            ],
        ]
    )


def get_change_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📂 Изменить категории",
                    callback_data="show_categories_main",
                )
            ],
            [InlineKeyboardButton(text="⚙️ Изменить фильтры", callback_data="show_filters_main")],
            [InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")],
        ]
    )


def get_back_to_filters_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад к фильтрам", callback_data="show_filters_main")]]
    )


def get_view_places_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✨ Смотреть места", callback_data="view_places_main")],
            [InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")],
        ]
    )


def get_moders_chat_del_keyboard(place_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑️ Удалить место", callback_data=f"mod_chat_del:{place_id}")],
        ]
    )


def get_moders_caht_del_approvement_keyboard(place_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да!", callback_data=f"approve_del:{place_id}")],
        ]
    )
