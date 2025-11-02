import logging

from aiogram import Bot, F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.base_keyboards import (
    get_back_to_filters_keyboard,
    get_back_to_main_keyboard,
    get_categories_keyboard,
    get_change_keyboard,
    get_filters_keyboard,
    get_main_keyboard,
    get_reset_geolocation_keyboard,
    get_update_keyboard,
    get_view_places_keyboard,
    get_wishes_keyboard,
)
from app.bot.constants import Constants
from app.bot.msgs_text import AVAILABLE_FILTERS, MsgsText
from app.bot.utils import delete_user_message, generate_place_text, show_place, update_or_send_message
from app.core.settings import Settings
from app.services.coordinator import Coordinator
from app.services.db_service import DbService
from app.services.redis_service import RedisService

logger = logging.getLogger(__name__)
base_router = Router()


MODERATORS_CHAT_ID = Settings.MODERATORS_CHAT_ID


# Состояния FSM
class FilterStates(StatesGroup):
    waiting_for_filter_name = State()


# отправка места на модерацию
@base_router.callback_query(F.data == "place_bad")
async def process_place_bad(callback_query: types.CallbackQuery, redis_service: RedisService, db_service: DbService):
    user_id = callback_query.from_user.id

    user = await db_service.get_user(user_id)
    user_data = redis_service.get_user_data(user_id)
    user_categories = user_data.get("selected_categories", [])
    user_wishes = user_data.get("selected_wishes", [])
    user_filters=user["filters"] if user else []
    places = user_data.get("places", [])
    index = user_data.get("current_place_index", 0)

    if not places or index >= len(places):
        await callback_query.answer("Ошибка: не удалось найти место для отправки.", show_alert=True)
        return

    place = places[index]

    # Формируем текст с рейтингом
    rating = place.get("rating")
    rating_text = f"⭐ {rating}/5" if rating else "⭐ Рейтинг не указан"

    # Получаем категории и пожелания места из базы данных
    categories_text, wishes_text, website = await db_service.get_categories_and_wishes(place)

    # Формируем текст
    place_text = generate_place_text(
        place, website, rating_text, categories_text=categories_text, wishes_text=wishes_text, user_categories=user_categories, user_filters=user_filters, user_wishes=user_wishes
    )

    photo_url = place.get("photo")

    # Уведомляем пользователя
    await callback_query.answer("Место отправлено на проверку ✅", show_alert=True)

    # Отправляем в чат модерации напрямую
    try:
        if photo_url and isinstance(photo_url, str) and photo_url.startswith(("http://", "https://")):
            if len(place_text) <= 1000:
                await callback_query.bot.send_photo(
                    chat_id=MODERATORS_CHAT_ID,
                    photo=photo_url,
                    caption=place_text,
                    parse_mode="HTML",
                )
            else:
                # Если текст слишком длинный
                await callback_query.bot.send_photo(chat_id=MODERATORS_CHAT_ID, photo=photo_url)
                await callback_query.bot.send_message(chat_id=MODERATORS_CHAT_ID, text=place_text, parse_mode="HTML")
        else:
            await callback_query.bot.send_message(chat_id=MODERATORS_CHAT_ID, text=place_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка отправки в чат модерации: {e}")
        await callback_query.bot.send_message(chat_id=MODERATORS_CHAT_ID, text=place_text, parse_mode="HTML")

    # Помечаем место как просмотренное
    await db_service.mark_place_as_viewed(user_id, place.get("name"))


@base_router.callback_query(F.data == "reset_location")
async def reset_location(
    callback: types.CallbackQuery,
    db_service: DbService,
    redis_service: RedisService,
    bot: Bot,
):
    user_id = callback.from_user.id
    user = await db_service.get_user(user_id)

    if user:
        # Сбрасываем геолокацию
        await db_service.create_or_update_user(
            user_id=user_id,
            categories=user["categories"],
            wishes=user["wishes"],
            filters=user["filters"],
            latitude=None,
            longitude=None,
        )

    # ПОЛНОСТЬЮ пересоздаем таблицу мест (так как изменилась геолокация)
    await db_service.create_user_places_relation(user_id)

    try:
        await callback.message.edit_text(text=MsgsText.RESET_GEO.value, reply_markup=get_reset_geolocation_keyboard())
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=MsgsText.RESET_GEO.value,
            bot=bot,
            redis_service=redis_service,
            reply_markup=get_reset_geolocation_keyboard(),
        )

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id)


@base_router.callback_query(F.data == "reset_viewed")
async def reset_viewed(callback: types.CallbackQuery, db_service: DbService):
    user_id = callback.from_user.id
    await db_service.reset_viewed(user_id)
    await callback.answer()


@base_router.callback_query(F.data == "reset_all_filters")
async def reset_all_filters(
    callback: types.CallbackQuery, db_service: DbService, redis_service: RedisService, bot: Bot
):
    user_id = callback.from_user.id

    # Сбрасываем все фильтры
    await db_service.save_user_filters(user_id, [])

    # Обновляем сообщение

    try:
        await callback.message.edit_text(
            text=MsgsText.NO_FILTERS.value, reply_markup=await get_filters_keyboard(user_id, db_service, 0)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=MsgsText.NO_FILTERS.value,
            bot=bot,
            redis_service=redis_service,
            reply_markup=await get_filters_keyboard(user_id, db_service, 0),
        )

    await callback.answer("Все фильтры сброшены")

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "reset_all_filters")


@base_router.callback_query(F.data == "reset_all_categories")
async def reset_all_categories(
    callback: types.CallbackQuery, redis_service: RedisService, db_service: DbService, bot: Bot
):
    user_id = callback.from_user.id

    # Сбрасываем все категории
    if f"data:{user_id}" in redis_service.get_keys("data:*"):
        redis_service.set_user_data_params(user_id, {"selected_categories": []})

    # Обновляем сообщение

    try:
        await callback.message.edit_text(
            text=MsgsText.CATEGORIES.value, reply_markup=get_categories_keyboard(user_id, redis_service)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=MsgsText.CATEGORIES.value,
            bot=bot,
            redis_service=redis_service,
            reply_markup=get_categories_keyboard(user_id, redis_service),
        )

    await callback.answer("Все категории сброшены")

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "reset_all_categories")


@base_router.callback_query(F.data == "reset_all_wishes")
async def reset_all_wishes(callback: types.CallbackQuery, redis_service: RedisService, db_service: DbService, bot: Bot):
    user_id = callback.from_user.id

    # Сбрасываем все пожелания
    if f"data:{user_id}" in redis_service.get_keys("data:*"):
        redis_service.set_user_data_params(user_id, {"selected_wishes": []})

    # Обновляем сообщение

    try:
        await callback.message.edit_text(
            text=MsgsText.WISHES.value, reply_markup=get_wishes_keyboard(user_id, redis_service)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=MsgsText.WISHES.value,
            bot=bot,
            redis_service=redis_service,
            reply_markup=get_wishes_keyboard(user_id, redis_service),
        )

    await callback.answer("Все пожелания сброшены")

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "reset_all_wishes")


# Обработчики команд
@base_router.message(Command("start"))
async def cmd_start(
    message: types.Message, redis_service: RedisService, db_service: DbService, coordinator: Coordinator, bot: Bot
):
    user_id = message.from_user.id
    chat_id = message.chat.id
    logger.info(f"User with {chat_id=} pressed start")
    # Загружаем данные пользователя из базы данных
    user_db_data = await db_service.get_user(user_id)
    if user_db_data:
        # Восстанавливаем настройки из базы данных
        redis_service.set_user_data(
            user_id,
            {
                "selected_categories": list(set(user_db_data["categories"])),
                "selected_wishes": list(set(user_db_data["wishes"])),
                "current_place_index": 0,
            },
        )
    else:
        # Создаем нового пользователя
        await coordinator.save_user(user_id)
        redis_service.set_user_data(
            user_id,
            {
                "selected_categories": [],
                "selected_wishes": [],
                "current_place_index": 0,
            },
        )

    photo = FSInputFile(Constants.START_IMG_PATH.value)

    # Сначала отправляем приветственное сообщение
    await update_or_send_message(
        chat_id=message.chat.id,
        text=MsgsText.WELCOME.value,
        bot=bot,
        redis_service=redis_service,
        reply_markup=get_main_keyboard(),
        photo_url=photo,
    )

    # Потом удаляем сообщение пользователя с командой start
    await delete_user_message(message)


@base_router.message(Command("help"))
async def help_cmd_handler(message: types.Message):
    await message.answer(text=MsgsText.HELP_TEXT.value, reply_markup=get_back_to_main_keyboard())


# Обработчики главного меню
@base_router.callback_query(F.data == "view_places_main")
async def show_places_main(callback: types.CallbackQuery, db_service: DbService, redis_service: RedisService, bot: Bot):
    user_id = callback.from_user.id
    user = await db_service.get_user(user_id)

    # Проверяем, есть ли непросмотренные места
    places = await db_service.get_places_for_user(user_id, limit=400, offset=0, sort_by_distance=False)

    if not places:
        # Все места просмотрены
        try:
            await callback.message.edit_text(text=MsgsText.ALL_VIEWED.value, reply_markup=get_update_keyboard())
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            chat_id = callback.message.chat.id
            await update_or_send_message(
                chat_id=chat_id,
                text=MsgsText.ALL_VIEWED.value,
                bot=bot,
                redis_service=redis_service,
                reply_markup=get_update_keyboard(),
            )

        await callback.answer()
        return
    # Проверяем, есть ли геолокация
    if user is not None and user["latitude"] is not None and user["longitude"] is not None:
        # Предлагаем выбор типа просмотра

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🗺️ Ближайшие места", callback_data="view_nearby_places")],
                [InlineKeyboardButton(text="⭐ Рекомендации", callback_data="view_recommended_places")],
                [InlineKeyboardButton(text="↩️ Назад", callback_data="main_menu")],
            ]
        )

        try:
            await callback.message.edit_text(text=MsgsText.VIEW_CHOICE.value, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            chat_id = callback.message.chat.id
            await update_or_send_message(
                chat_id=chat_id,
                text=MsgsText.VIEW_CHOICE.value,
                bot=bot,
                redis_service=redis_service,
                reply_markup=keyboard,
            )
    else:
        # Если нет геолокации, показываем обычные рекомендации
        redis_service.set_user_data_params(user_id, {"current_place_index": 0})
        redis_service.set_user_data_params(user_id, {"current_offset": 0})

        # Сохраняем места для пользователя
        redis_service.set_user_data_params(user_id, {"places": places})

        # Показываем первое место
        await show_place(user_id, callback.message.chat.id, 0, bot, db_service, redis_service)

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "view_places_main")


@base_router.callback_query(F.data == "view_nearby_places")
async def view_nearby_places(
    callback: types.CallbackQuery, redis_service: RedisService, db_service: DbService, bot: Bot
):
    user_id = callback.from_user.id
    redis_service.set_user_data_params(user_id, {"current_place_index": 0})
    redis_service.set_user_data_params(user_id, {"current_offset": 0})

    # Получаем места с сортировкой по расстоянию
    places = await db_service.get_places_for_user(user_id, limit=400, offset=0, sort_by_distance=True)

    if not places:
        # Обработка случая, когда нет мест

        keyboard = get_change_keyboard()
        try:
            await callback.message.edit_text(text=MsgsText.NO_PLACES_NEAR.value, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            chat_id = callback.message.chat.id
            await update_or_send_message(
                chat_id=chat_id,
                text=MsgsText.NO_PLACES_NEAR.value,
                bot=bot,
                redis_service=redis_service,
                reply_markup=keyboard,
            )

        await callback.answer()
        return

    # Сохраняем места для пользователя
    redis_service.set_user_data_params(user_id, {"places": places})

    # Показываем первое место
    await show_place(user_id, callback.message.chat.id, 0, bot, db_service, redis_service)

    await callback.answer()


@base_router.callback_query(F.data == "view_recommended_places")
async def view_recommended_places(
    callback: types.CallbackQuery, redis_service: RedisService, db_service: DbService, bot: Bot
):
    user_id = callback.from_user.id
    redis_service.set_user_data_params(user_id, {"current_place_index": 0})
    redis_service.set_user_data_params(user_id, {"current_offset": 0})

    # Получаем места без сортировки по расстоянию
    places = await db_service.get_places_for_user(user_id, limit=400, offset=0, sort_by_distance=False)

    if not places:
        # Обработка случая, когда нет мест
        keyboard = get_change_keyboard()

        try:
            await callback.message.edit_text(text=MsgsText.NO_PLACES.value, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            chat_id = callback.message.chat.id
            await update_or_send_message(
                chat_id=chat_id,
                text=MsgsText.NO_PLACES.value,
                bot=bot,
                redis_service=redis_service,
                reply_markup=keyboard,
            )

        await callback.answer()
        return

    # Сохраняем места для пользователя
    redis_service.set_user_data_params(user_id, {"places": places})

    # Показываем первое место
    await show_place(user_id, callback.message.chat.id, 0, bot, db_service, redis_service)

    await callback.answer()


@base_router.callback_query(F.data == "show_categories_main")
async def show_categories_main(
    callback: types.CallbackQuery, redis_service: RedisService, db_service: DbService, bot: Bot
):
    try:
        await callback.message.edit_text(
            text=MsgsText.CATEGORIES.value,
            reply_markup=get_categories_keyboard(callback.from_user.id, redis_service),
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=MsgsText.CATEGORIES.value,
            bot=bot,
            redis_service=redis_service,
            reply_markup=get_categories_keyboard(callback.from_user.id, redis_service),
        )

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "show_categories_main")


@base_router.callback_query(F.data == "show_filters_main")
async def show_filters_main(
    callback: types.CallbackQuery, db_service: DbService, redis_service: RedisService, bot: Bot
):
    user_id = callback.from_user.id
    user_filters = await db_service.get_user_filters(user_id)

    filters_text = MsgsText.FILTERS.value

    if user_filters:
        for filter_name in user_filters:
            filters_text += f"• {filter_name}\n"
    else:
        filters_text += "❌ Фильтры не выбраны\n"

    filters_text += "\nПосле выбора нажмите 'Подтвердить'"

    try:
        await callback.message.edit_text(
            text=filters_text, reply_markup=await get_filters_keyboard(user_id, db_service, 0)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=filters_text,
            bot=bot,
            redis_service=redis_service,
            reply_markup=await get_filters_keyboard(user_id, db_service, 0),
        )

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "show_filters_main")


@base_router.callback_query(F.data.startswith("filters_page_"))
async def handle_filters_page(
    callback: types.CallbackQuery, db_service: DbService, redis_service: RedisService, bot: Bot
):
    user_id = callback.from_user.id
    page = int(callback.data.split("_")[2])

    user_filters = await db_service.get_user_filters(user_id)

    filters_text = MsgsText.FILTERS.value

    if user_filters:
        for filter_name in user_filters:
            filters_text += f"• {filter_name}\n"
    else:
        filters_text += "❌ Фильтры не выбраны\n"

    filters_text += "\nПосле выбора нажмите 'Подтвердить'"

    try:
        await callback.message.edit_text(
            text=filters_text, reply_markup=await get_filters_keyboard(user_id, db_service, page)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=filters_text,
            bot=bot,
            redis_service=redis_service,
            reply_markup=await get_filters_keyboard(user_id, db_service, page),
        )

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id)


@base_router.callback_query(F.data.startswith("filter_"))
async def handle_filter_selection(
    callback: types.CallbackQuery, db_service: DbService, redis_service: RedisService, bot: Bot
):
    user_id = callback.from_user.id

    # Разбираем callback_data: filter_индекс_страница
    parts = callback.data.split("_")
    filter_index = int(parts[1])
    current_page = int(parts[2])

    # Получаем название фильтра по индексу
    filter_name = AVAILABLE_FILTERS[filter_index]

    user_filters = await db_service.get_user_filters(user_id)

    # Переключаем состояние фильтра
    if filter_name in user_filters:
        user_filters.remove(filter_name)
    else:
        user_filters.append(filter_name)

    # Сохраняем фильтры
    await db_service.save_user_filters(user_id, user_filters)

    # Обновляем сообщение
    user_filters = await db_service.get_user_filters(user_id)

    filters_text = MsgsText.FILTERS.value

    if user_filters:
        for filter_name in user_filters:
            filters_text += f"• {filter_name}\n"
    else:
        filters_text += "❌ Фильтры не выбраны\n"

    filters_text += "\nПосле выбора нажмите 'Подтвердить'"

    try:
        await callback.message.edit_text(
            text=filters_text, reply_markup=await get_filters_keyboard(user_id, db_service, current_page)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=filters_text,
            bot=bot,
            redis_service=redis_service,
            reply_markup=await get_filters_keyboard(user_id, db_service, current_page),
        )

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id)


@base_router.callback_query(F.data == "search_filter")
async def search_filter(
    callback: types.CallbackQuery, state: FSMContext, db_service: DbService, redis_service: RedisService, bot: Bot
):
    try:
        await callback.message.edit_text(text=MsgsText.SEARCH_FILTER.value, reply_markup=get_back_to_filters_keyboard())
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=MsgsText.SEARCH_FILTER.value,
            bot=bot,
            redis_service=redis_service,
            reply_markup=get_back_to_filters_keyboard(),
        )

    # Устанавливаем состояние ожидания названия фильтра
    await state.set_state(FilterStates.waiting_for_filter_name)
    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id)


@base_router.message(FilterStates.waiting_for_filter_name)
async def process_filter_search(
    message: types.Message, state: FSMContext, db_service: DbService, redis_service: RedisService, bot: Bot
):
    user_id = message.from_user.id
    filter_name = message.text.strip()

    # Проверяем, существует ли такой фильтр
    if filter_name in AVAILABLE_FILTERS:
        # Добавляем фильтр
        user_filters = await db_service.get_user_filters(user_id)
        user_filters.append(filter_name)
        await db_service.save_user_filters(user_id, user_filters)

        # Находим страницу, на которой находится этот фильтр
        filter_index = AVAILABLE_FILTERS.index(filter_name)
        filter_page = filter_index // 8

        success_text = f"""
✅ <b>Фильтр добавлен</b>

Фильтр "{filter_name}" успешно добавлен к вашим настройкам.
    """

        await update_or_send_message(
            chat_id=message.chat.id,
            text=success_text,
            bot=bot,
            redis_service=redis_service,
            reply_markup=await get_filters_keyboard(user_id, db_service, filter_page),  # Переходим на страницу фильтра
        )
    else:
        error_text = f"""
❌ <b>Фильтр не найден</b>

Фильтр "{filter_name}" не существует. 
Пожалуйста, выберите фильтр из доступного списка.
    """

        await update_or_send_message(
            chat_id=message.chat.id,
            text=error_text,
            bot=bot,
            reply_markup=await get_filters_keyboard(user_id, db_service, 0),
        )

    # Сбрасываем состояние
    await state.clear()

    # Удаляем сообщение пользователя
    await delete_user_message(message)

    # Обновляем время последней активности
    await db_service.update_user_activity(message.from_user.id)


@base_router.callback_query(F.data == "confirm_filters")
async def confirm_filters(callback: types.CallbackQuery, db_service: DbService, redis_service: RedisService, bot: Bot):
    user_id = callback.from_user.id
    user_filters = await db_service.get_user_filters(user_id)

    # Показываем сообщение о процессе подбора
    processing_message_id = await update_or_send_message(
        callback.message.chat.id,
        MsgsText.PROCESSING.value,
        bot=bot,
        redis_service=redis_service,
    )

    await db_service.create_user_places_relation(user_id)

    confirmation_text = f"""
✅ <b>Фильтры сохранены!</b>

<b>Выбрано фильтров:</b> {len(user_filters)}

Теперь вы можете просматривать места, соответствующие вашим предпочтениям.
    """

    try:
        await callback.message.edit_text(text=confirmation_text, reply_markup=get_view_places_keyboard())
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id

        # Удаляем сообщение о процессе
        if processing_message_id:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=processing_message_id)
            except Exception as e:
                logger.error(f"Error while deleting msh {e}")

        await update_or_send_message(
            chat_id=chat_id,
            text=confirmation_text,
            bot=bot,
            redis_service=redis_service,
            reply_markup=get_view_places_keyboard(),
        )

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "confirm_filters")


@base_router.callback_query(F.data == "show_geolocation_main")
async def show_geolocation_main(
    callback: types.CallbackQuery, db_service: DbService, redis_service: RedisService, bot: Bot
):
    user_id = callback.from_user.id
    user = await db_service.get_user(user_id)

    geo_text = """
🗺️ <b>Поиск по геолокации</b>

Отправьте ваше местоположение, чтобы найти места рядом с вами.
    """

    if user and user["latitude"] is not None and user["longitude"] is not None:
        geo_text += f"""
<b>Текущее местоположение сохранено</b>
✨ Широта: {user["latitude"]:.6f}
✨ Долгота: {user["longitude"]:.6f}

Теперь вы можете смотреть места рядом с вами.
    """
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✨ Смотреть места рядом", callback_data="view_places_main")],
                [InlineKeyboardButton(text="🗺️ Обновить геолокацию", callback_data="request_location")],
                [InlineKeyboardButton(text="❌ Сбросить геолокацию", callback_data="reset_location")],
                [InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")],
            ]
        )
    else:
        geo_text += """
❌ <b>Местоположение не указано</b>

Пожалуйста, отправьте ваше местоположение.
    """
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🗺️ Отправить геолокацию", callback_data="request_location")],
                [InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")],
            ]
        )

    try:
        await callback.message.edit_text(text=geo_text, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id, text=geo_text, bot=bot, redis_service=redis_service, reply_markup=keyboard
        )

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "show_geolocation_main")


@base_router.callback_query(F.data == "request_location")
async def request_location(callback: types.CallbackQuery, redis_service: RedisService, bot: Bot):
    try:
        await callback.message.edit_text(
            text=MsgsText.SEND_LOCATION.value,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="show_geolocation_main")]]
            ),
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=MsgsText.SEND_LOCATION.value,
            bot=bot,
            redis_service=redis_service,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="show_geolocation_main")]]
            ),
        )

    await callback.answer()


@base_router.message(F.content_type == "location")
async def handle_location(message: types.Message, db_service: DbService, redis_service: RedisService, bot: Bot):
    user_id = message.from_user.id
    latitude = message.location.latitude
    longitude = message.location.longitude

    # Сохраняем геолокацию пользователя
    user = await db_service.get_user(user_id)
    if user:
        await db_service.create_or_update_user(
            user_id=user_id,
            categories=user["categories"],
            wishes=user["wishes"],
            filters=user["filters"],
            latitude=latitude,
            longitude=longitude,
        )
    else:
        # Если пользователя нет в базе, создаем запись
        await db_service.create_or_update_user(
            user_id=user_id, categories=[], wishes=[], filters=[], latitude=latitude, longitude=longitude
        )

    # пересоздаем таблицу мест с новой геолокацией
    await db_service.create_user_places_relation(user_id)

    # Отправляем подтверждение

    await update_or_send_message(
        chat_id=message.chat.id,
        text=MsgsText.GEO_SAVED.value,
        bot=bot,
        redis_service=redis_service,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✨ Смотреть места рядом", callback_data="view_places_main")],
                [InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")],
            ]
        ),
    )

    # Удаляем сообщение с геолокацией
    await delete_user_message(message)

    # Обновляем время последней активности
    await db_service.update_user_activity(message.from_user.id)


@base_router.callback_query(F.data == "show_help_main")
async def show_help_main(callback: types.CallbackQuery, db_service: DbService, redis_service: RedisService, bot: Bot):
    try:
        await callback.message.edit_text(text=MsgsText.HELP_TEXT.value, reply_markup=get_back_to_main_keyboard())
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=MsgsText.HELP_TEXT.value,
            bot=bot,
            redis_service=redis_service,
            reply_markup=get_back_to_main_keyboard(),
        )

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "show_help_main")


# Обработчики инлайн кнопок
@base_router.callback_query(F.data.in_(MsgsText.CATEGORIES_TYPES.value))
async def handle_category_selection(
    callback: types.CallbackQuery, redis_service: RedisService, db_service: DbService, bot: Bot
):
    user_id = callback.from_user.id
    category = callback.data

    if f"data:{user_id}" not in redis_service.get_keys("data:*"):
        redis_service.set_user_data(user_id, {"selected_categories": [], "selected_wishes": []})

    user_data = redis_service.get_user_data(user_id)
    if category in user_data["selected_categories"]:
        user_data["selected_categories"].remove(category)
    else:
        user_data["selected_categories"].append(category)
    redis_service.set_user_data(user_id, user_data)

    # Обновляем сообщение с новым состоянием кнопок

    try:
        await callback.message.edit_text(
            text=MsgsText.CATEGORIES.value, reply_markup=get_categories_keyboard(user_id, redis_service)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        # Если не удалось отредактировать, отправляем новое сообщение
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=MsgsText.CATEGORIES.value,
            bot=bot,
            redis_service=redis_service,
            reply_markup=get_categories_keyboard(user_id, redis_service),
        )

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id)


@base_router.callback_query(F.data == "confirm_categories")
async def confirm_categories(
    callback: types.CallbackQuery, redis_service: RedisService, db_service: DbService, bot: Bot
):
    try:
        await callback.message.edit_text(
            text=MsgsText.WISHES.value, reply_markup=get_wishes_keyboard(callback.from_user.id, redis_service)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=MsgsText.WISHES.value,
            bot=bot,
            redis_service=redis_service,
            reply_markup=get_wishes_keyboard(callback.from_user.id, redis_service),
        )

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "confirm_categories")


@base_router.callback_query(F.data.in_(MsgsText.WISHES_TYPES.value))
async def handle_wish_selection(
    callback: types.CallbackQuery, redis_service: RedisService, db_service: DbService, bot: Bot
):
    user_id = callback.from_user.id
    wish = callback.data

    if f"data:{user_id}" not in redis_service.get_keys("data:*"):
        redis_service.set_user_data(user_id, {"selected_categories": [], "selected_wishes": []})

    user_data = redis_service.get_user_data(user_id)

    if wish in user_data["selected_wishes"]:
        user_data["selected_wishes"].remove(wish)
    else:
        user_data["selected_wishes"].append(wish)

    redis_service.set_user_data(user_id, user_data)

    # Обновляем сообщение

    try:
        await callback.message.edit_text(
            text=MsgsText.WISHES.value, reply_markup=get_wishes_keyboard(user_id, redis_service)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=MsgsText.WISHES.value,
            bot=bot,
            redis_service=redis_service,
            reply_markup=get_wishes_keyboard(user_id, redis_service),
        )

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id)


@base_router.callback_query(F.data == "confirm_wishes")
async def confirm_wishes(
    callback: types.CallbackQuery,
    redis_service: RedisService,
    db_service: DbService,
    bot: Bot,
):
    user_id = callback.from_user.id

    user_data = redis_service.get_user_data(user_id)
    categories_count = len(user_data["selected_categories"])
    wishes_count = len(user_data["selected_wishes"])

    # Показываем сообщение о процессе подбора

    processing_message_id = await update_or_send_message(
        callback.message.chat.id,
        MsgsText.PROCESSING.value,
        bot=bot,
        redis_service=redis_service,
    )

    # Получаем текущие данные пользователя из базы (включая геопозицию)
    user = await db_service.get_user(user_id)

    # Сохраняем пользователя в базу данных с сохранением геопозиции
    await db_service.create_or_update_user(
        user_id=user_id,
        categories=user_data["selected_categories"],
        wishes=user_data["selected_wishes"],
        filters=user["filters"] if user else [],  # Сохраняем текущие фильтры
        latitude=user["latitude"] if user else None,  # Сохраняем геопозицию
        longitude=user["longitude"] if user else None,  # Сохраняем геопозицию
    )

    await db_service.create_user_places_relation(user_id)

    confirmation_text = f"""
<b>Настройки сохранены!</b>

<b>Выбрано категорий:</b> {categories_count}
<b>Выбрано пожеланий:</b> {wishes_count}
<b>Выбрано фильтры:</b> {len(user["filters"]) if user else 0}

История просмотров сброшена. Теперь вы можете просматривать места, соответствующие вашим новым предпочтениям.
        """

    try:
        await callback.message.edit_text(text=confirmation_text, reply_markup=get_view_places_keyboard())
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id

        # Удаляем сообщение о процессе
        if processing_message_id:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=processing_message_id)
            except Exception as e:
                logger.error(f"Error while deleting msg {e}")

        await update_or_send_message(
            chat_id=chat_id,
            text=confirmation_text,
            bot=bot,
            redis_service=redis_service,
            reply_markup=get_view_places_keyboard(),
        )

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "confirm_wishes")


@base_router.callback_query(F.data == "main_menu")
async def back_to_main_menu(
    callback: types.CallbackQuery, db_service: DbService, redis_service: RedisService, bot: Bot
):
    photo = FSInputFile(Constants.START_IMG_PATH.value)

    chat_id = callback.message.chat.id

    await update_or_send_message(
        chat_id=chat_id,
        text=MsgsText.WELCOME.value,
        bot=bot,
        redis_service=redis_service,
        reply_markup=get_main_keyboard(),
        photo_url=photo,
    )
    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "main_menu")


@base_router.callback_query(F.data.in_(["place_prev", "place_next"]))
async def navigate_places(callback: types.CallbackQuery, redis_service: RedisService, db_service: DbService, bot: Bot):
    user_id = callback.from_user.id
    user_data = redis_service.get_user_data(user_id)
    current_index = user_data.get("current_place_index", 0)
    places = user_data.get("places", [])

    if not places:
        await callback.answer("Нет мест для показа")
        return

    if callback.data == "place_prev":
        if current_index > 0:
            current_index -= 1
        else:
            await callback.answer("Это первое место")
            return
    else:  # place_next
        if current_index < len(places) - 1:
            current_index += 1
        else:
            # Все места просмотрены - показываем сообщение/меню

            keyboard = get_update_keyboard()
            try:
                await callback.message.edit_text(text=MsgsText.ALL_VIEWED.value, reply_markup=keyboard)
            except Exception as e:
                logger.error(f"Error editing message: {e}")
                chat_id = callback.message.chat.id
                await update_or_send_message(
                    chat_id=chat_id,
                    text=MsgsText.ALL_VIEWED.value,
                    bot=bot,
                    redis_service=redis_service,
                    reply_markup=keyboard,
                )
            await callback.answer()
            return

    redis_service.set_user_data_params(user_id, {"current_place_index": current_index})

    # Показываем место
    await show_place(user_id, callback.message.chat.id, current_index, bot, db_service, redis_service)

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id)


# Обработчик отмены состояния фильтра
@base_router.callback_query(F.data == "show_filters_main", FilterStates.waiting_for_filter_name)
async def cancel_filter_search(
    callback: types.CallbackQuery, state: FSMContext, db_service: DbService, redis_service: RedisService, bot: Bot
):
    user_id = callback.from_user.id
    user_filters = await db_service.get_user_filters(user_id)

    filters_text = MsgsText.FILTERS.value

    if user_filters:
        for filter_name in user_filters:
            filters_text += f"• {filter_name}\n"
    else:
        filters_text += "❌ Фильтры не выбраны\n"

    filters_text += "\nПосле выбора нажмите 'Подтвердить'"

    try:
        await callback.message.edit_text(
            text=filters_text, reply_markup=await get_filters_keyboard(user_id, db_service, 0)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=filters_text,
            bot=bot,
            redis_service=redis_service,
            reply_markup=await get_filters_keyboard(user_id, db_service, 0),
        )

    # Сбрасываем состояние
    await state.clear()

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id)


# Обработчик всех текстовых сообщений (удаление)
@base_router.message(~F.chat.id.in_(Constants.ADMIN_IDS.value))
async def delete_all_messages(message: types.Message, db_service: DbService):
    await delete_user_message(message)

    # Обновляем время последней активности
    await db_service.update_user_activity(message.from_user.id)
