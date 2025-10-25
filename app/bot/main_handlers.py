import logging
from math import atan2, cos, radians, sin, sqrt

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards import (
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
from app.bot.msg_constants import AVAILABLE_FILTERS, MsgConstants
from app.bot.utils import generate_place_text
from app.core.instances import bot, db_service, redis_service
from app.core.settings import Settings

logger = logging.getLogger(__name__)
main_router = Router()


MODERATORS_CHAT_ID = Settings.MODERATORS_CHAT_ID
START_IMG_PATH = "app/data/images/start_img.jpg"


# Состояния FSM
class FilterStates(StatesGroup):
    waiting_for_filter_name = State()


# отправка места на модерацию
@main_router.callback_query(F.data == "place_bad")
async def process_place_bad(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id

    user_data = redis_service.get_user_data(user_id)
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
    place_text = generate_place_text(place, website, rating_text)

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


@main_router.callback_query(F.data == "reset_location")
async def reset_location(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await db_service.get_user(user_id)

    if user:
        # Сбрасываем геолокацию
        await db_service.save_user(
            user_id=user_id,
            categories=user["categories"],
            wishes=user["wishes"],
            filters=user["filters"],
            latitude=None,
            longitude=None,
        )

    # ПОЛНОСТЬЮ пересоздаем таблицу мест (так как изменилась геолокация)
    await db_service.create_user_places_table(user_id)

    try:
        await callback.message.edit_text(
            text=MsgConstants.RESET_GEO.value, reply_markup=get_reset_geolocation_keyboard()
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id, text=MsgConstants.RESET_GEO.value, reply_markup=get_reset_geolocation_keyboard()
        )

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id)


@main_router.callback_query(F.data == "reset_viewed")
async def reset_viewed(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await db_service.reset_viewed(user_id)
    await callback.answer()


@main_router.callback_query(F.data == "reset_all_filters")
async def reset_all_filters(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    # Сбрасываем все фильтры
    await db_service.save_user_filters(user_id, [])

    # Обновляем сообщение

    try:
        await callback.message.edit_text(
            text=MsgConstants.NO_FILTERS.value, reply_markup=await get_filters_keyboard(user_id, 0)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=MsgConstants.NO_FILTERS.value,
            reply_markup=await get_filters_keyboard(user_id, 0),
        )

    await callback.answer("Все фильтры сброшены")

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "reset_all_filters")


@main_router.callback_query(F.data == "reset_all_categories")
async def reset_all_categories(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    # Сбрасываем все категории
    if f"data:{user_id}" in redis_service.get_keys("data:*"):
        redis_service.set_user_data_params(user_id, {"selected_categories": []})

    # Обновляем сообщение

    try:
        await callback.message.edit_text(
            text=MsgConstants.CATEGORIES.value, reply_markup=get_categories_keyboard(user_id)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=MsgConstants.CATEGORIES.value,
            reply_markup=get_categories_keyboard(user_id),
        )

    await callback.answer("Все категории сброшены")

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "reset_all_categories")


@main_router.callback_query(F.data == "reset_all_wishes")
async def reset_all_wishes(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    # Сбрасываем все пожелания
    if f"data:{user_id}" in redis_service.get_keys("data:*"):
        redis_service.set_user_data_params(user_id, {"selected_wishes": []})

    # Обновляем сообщение

    try:
        await callback.message.edit_text(text=MsgConstants.WISHES.value, reply_markup=get_wishes_keyboard(user_id))
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id, text=MsgConstants.WISHES.value, reply_markup=get_wishes_keyboard(user_id)
        )

    await callback.answer("Все пожелания сброшены")

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "reset_all_wishes")


async def show_place(user_id: int, chat_id: int, index: int):
    logger.info(f"show_place {user_id=}")
    places = redis_service.get_user_data(user_id).get("places", [])
    logger.info(f"{len(places)=}")

    if not places or index >= len(places):
        return

    place = places[index]

    # Формируем текст с рейтингом
    rating = place.get("rating")
    rating_text = f"⭐ {rating}/5" if rating else "⭐ Рейтинг не указан"

    # Получаем категории и пожелания места из базы данных

    # Формируем текст с категориями и пожеланиями
    categories_text, wishes_text, website = await db_service.get_categories_and_wishes(place)
    # Получаем геолокацию пользователя
    user = await db_service.get_user(user_id)

    distance_text = ""

    if user and user["latitude"] and user["longitude"] and place.get("latitude") and place.get("longitude"):
        try:
            user_lat = user["latitude"]
            user_lon = user["longitude"]
            place_lat = float(place["latitude"])
            place_lon = float(place["longitude"])

            # Расчет расстояния
            R = 6371  # Радиус Земли в км
            lat1_rad = radians(user_lat)
            lon1_rad = radians(user_lon)
            lat2_rad = radians(place_lat)
            lon2_rad = radians(place_lon)

            dlon = lon2_rad - lon1_rad
            dlat = lat2_rad - lat1_rad

            a = sin(dlat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2) ** 2
            c = 2 * atan2(sqrt(a), sqrt(1 - a))

            distance = R * c
            distance_text = f"\n<b>Расстояние:</b> {distance:.1f} км от вас"

        except (ValueError, TypeError):
            # Если координаты некорректны, пропускаем
            pass
    logger.info(len(places))
    place_text = generate_place_text(place, website, rating_text, distance_text)

    # Получаем ссылку на фото и проверяем ее валидность
    photo_url = place.get("photo")

    # Проверяем, является ли photo_url валидной ссылкой
    if photo_url and isinstance(photo_url, str) and photo_url.startswith(("http://", "https://")):
        try:
            await update_or_send_message(
                chat_id=chat_id,
                text=place_text,
                reply_markup=get_places_keyboard(),
                photo_url=photo_url,
            )
        except Exception as e:
            logger.error(f"Error sending photo message: {e}")
            # Если не удалось отправить с фото, отправляем без фото
            await update_or_send_message(chat_id=chat_id, text=place_text, reply_markup=get_places_keyboard())
    else:
        # Если фото нет или ссылка невалидна, отправляем без фото
        await update_or_send_message(chat_id=chat_id, text=place_text, reply_markup=get_places_keyboard())
    # Помечаем место как просмотренное по названию
    await db_service.mark_place_as_viewed(user_id, place.get("name"))


# Функции для работы с сообщениями


async def delete_user_message(message: types.Message):
    """Удалить сообщение пользователя"""
    try:
        await message.delete()
    except Exception as e:
        logger.error(f"Error while deleting user msg, {e}")


async def update_or_send_message(chat_id: int, text: str, reply_markup=None, photo_url: str = None):
    """Обновить существующее сообщение или отправить новое"""
    logger.info("update_or_send")
    last_msg = redis_service.get_user_msg(chat_id)
    if last_msg:
        try:
            if photo_url:
                # Если есть фото, отправляем новое сообщение с фото
                message = await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_url,
                    caption=text,
                    reply_markup=reply_markup,
                )
                # Удаляем старое сообщение
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=last_msg)
                except Exception as e:
                    logger.error(f"Error while deleting user msg, {e}")
            else:
                # Если нет фото, пытаемся отредактировать текстовое сообщение
                try:
                    message = await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=last_msg,
                        text=text,
                        reply_markup=reply_markup,
                    )
                except Exception as edit_error:
                    # Если не удалось отредактировать, отправляем новое сообщение
                    logger.error(f"Error editing message, sending new: {edit_error}")
                    message = await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
                    # Пытаемся удалить старое сообщение
                    try:
                        await bot.delete_message(chat_id=chat_id, message_id=last_msg)
                    except Exception as e:
                        logger.error(f"Error while deleting user msg, {e}")

            redis_service.set_user_msg(chat_id, message.message_id)
            return message.message_id
        except Exception as e:
            logger.error(f"Error in update_or_send_message: {e}")
            # Если все попытки не удались, отправляем новое сообщение
            try:
                if photo_url:
                    message = await bot.send_photo(
                        chat_id=chat_id,
                        photo=photo_url,
                        caption=text,
                        reply_markup=reply_markup,
                    )
                else:
                    message = await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
                redis_service.set_user_msg(chat_id, message.message_id)
                return message.message_id
            except Exception as e2:
                logger.error(f"Error sending new message: {e2}")
                return None
    else:
        try:
            if photo_url:
                message = await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_url,
                    caption=text,
                    reply_markup=reply_markup,
                )
            else:
                message = await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
            redis_service.set_user_msg(chat_id, message.message_id)
            return message.message_id
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return None


# Обработчики команд
@main_router.message(Command("start"))
async def cmd_start(message: types.Message):
    logger.info("cmd_start")
    user_id = message.from_user.id
    chat_id = message.chat.id
    logger.info(f"User with {chat_id=} press start")
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
        # Создаем нового пользователя в памяти (но не в базе до выбора категорий)
        await db_service.save_user(user_id)
        redis_service.set_user_data(
            user_id,
            {
                "selected_categories": [],
                "selected_wishes": [],
                "current_place_index": 0,
            },
        )

    photo = FSInputFile(START_IMG_PATH)

    # Сначала отправляем приветственное сообщение
    await update_or_send_message(
        chat_id=message.chat.id, text=MsgConstants.WELCOME.value, reply_markup=get_main_keyboard(), photo_url=photo
    )

    # Потом удаляем сообщение пользователя с командой start
    await delete_user_message(message)


@main_router.message(Command("stats"))  # need fix
async def daily_report(message: types.Message = None, by_timer=False):
    chat_id = message.chat.id
    if by_timer:
        stats = db_service.user_count
        stat_message = f"""
    <b>Статистика пользователей<b>
    Сегодня {stats[0]} новых пользователей
    Всего {stats[1]} пользователей
        """
        bot.send_message(chat_id=Settings.MODERATORS_CHAT_ID, text=stat_message, parse_mode="HTML")
        db_service.change_user_count(reset=True)
    else:
        if chat_id == Settings.MODERATORS_CHAT_ID:
            stats = await db_service.user_counts()
            stat_message = f"""
        <b>Статистика пользователей</b>
        Сегодня {stats[0]} новых пользователей
        Всего {stats[1]} пользователей
            """
            await bot.send_message(chat_id=Settings.MODERATORS_CHAT_ID, text=stat_message, parse_mode="HTML")


# Обработчики главного меню
@main_router.callback_query(F.data == "view_places_main")
async def show_places_main(callback: types.CallbackQuery):
    logger.info("show_places_main")
    user_id = callback.from_user.id
    user = await db_service.get_user(user_id)

    # Проверяем, есть ли непросмотренные места
    places = await db_service.get_places_for_user(user_id, limit=400, offset=0, sort_by_distance=False)

    if not places:
        # Все места просмотрены
        try:
            await callback.message.edit_text(text=MsgConstants.ALL_VIEWED.value, reply_markup=get_update_keyboard())
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            chat_id = callback.message.chat.id
            await update_or_send_message(
                chat_id=chat_id, text=MsgConstants.ALL_VIEWED.value, reply_markup=get_update_keyboard()
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
            await callback.message.edit_text(text=MsgConstants.VIEW_CHOICE.value, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            chat_id = callback.message.chat.id
            await update_or_send_message(chat_id=chat_id, text=MsgConstants.VIEW_CHOICE.value, reply_markup=keyboard)
    else:
        # Если нет геолокации, показываем обычные рекомендации
        redis_service.set_user_data_params(user_id, {"current_place_index": 0})
        redis_service.set_user_data_params(user_id, {"current_offset": 0})

        # Сохраняем места для пользователя
        redis_service.set_user_data_params(user_id, {"places": places})

        # Показываем первое место
        await show_place(user_id, callback.message.chat.id, 0)

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "view_places_main")


@main_router.callback_query(F.data == "view_nearby_places")
async def view_nearby_places(callback: types.CallbackQuery):
    logger.info("view_nearby")
    user_id = callback.from_user.id
    redis_service.set_user_data_params(user_id, {"current_place_index": 0})
    redis_service.set_user_data_params(user_id, {"current_offset": 0})

    # Получаем места с сортировкой по расстоянию
    places = await db_service.get_places_for_user(user_id, limit=400, offset=0, sort_by_distance=True)

    if not places:
        # Обработка случая, когда нет мест

        keyboard = get_change_keyboard()
        try:
            await callback.message.edit_text(text=MsgConstants.NO_PLACES_NEAR.value, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            chat_id = callback.message.chat.id
            await update_or_send_message(chat_id=chat_id, text=MsgConstants.NO_PLACES_NEAR.value, reply_markup=keyboard)

        await callback.answer()
        return

    # Сохраняем места для пользователя
    redis_service.set_user_data_params(user_id, {"places": places})

    # Показываем первое место
    await show_place(user_id, callback.message.chat.id, 0)

    await callback.answer()


@main_router.callback_query(F.data == "view_recommended_places")
async def view_recommended_places(callback: types.CallbackQuery):
    logger.info("view_recommended")
    user_id = callback.from_user.id
    redis_service.set_user_data_params(user_id, {"current_place_index": 0})
    redis_service.set_user_data_params(user_id, {"current_offset": 0})

    # Получаем места без сортировки по расстоянию
    places = await db_service.get_places_for_user(user_id, limit=400, offset=0, sort_by_distance=False)

    if not places:
        # Обработка случая, когда нет мест
        keyboard = get_change_keyboard()

        try:
            await callback.message.edit_text(text=MsgConstants.NO_PLACES.value, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            chat_id = callback.message.chat.id
            await update_or_send_message(chat_id=chat_id, text=MsgConstants.NO_PLACES.value, reply_markup=keyboard)

        await callback.answer()
        return

    # Сохраняем места для пользователя
    redis_service.set_user_data_params(user_id, {"places": places})

    # Показываем первое место
    await show_place(user_id, callback.message.chat.id, 0)

    await callback.answer()


@main_router.callback_query(F.data == "show_categories_main")
async def show_categories_main(callback: types.CallbackQuery):
    try:
        await callback.message.edit_text(
            text=MsgConstants.CATEGORIES.value,
            reply_markup=get_categories_keyboard(callback.from_user.id),
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=MsgConstants.CATEGORIES.value,
            reply_markup=get_categories_keyboard(callback.from_user.id),
        )

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "show_categories_main")


@main_router.callback_query(F.data == "show_filters_main")
async def show_filters_main(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_filters = await db_service.get_user_filters(user_id)

    filters_text = MsgConstants.FILTERS.value

    if user_filters:
        for filter_name in user_filters:
            filters_text += f"• {filter_name}\n"
    else:
        filters_text += "❌ Фильтры не выбраны\n"

    filters_text += "\nПосле выбора нажмите 'Подтвердить'"

    try:
        await callback.message.edit_text(text=filters_text, reply_markup=await get_filters_keyboard(user_id, 0))
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=filters_text,
            reply_markup=await get_filters_keyboard(user_id, 0),
        )

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "show_filters_main")


@main_router.callback_query(F.data.startswith("filters_page_"))
async def handle_filters_page(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    page = int(callback.data.split("_")[2])

    user_filters = await db_service.get_user_filters(user_id)

    filters_text = MsgConstants.FILTERS.value

    if user_filters:
        for filter_name in user_filters:
            filters_text += f"• {filter_name}\n"
    else:
        filters_text += "❌ Фильтры не выбраны\n"

    filters_text += "\nПосле выбора нажмите 'Подтвердить'"

    try:
        await callback.message.edit_text(text=filters_text, reply_markup=await get_filters_keyboard(user_id, page))
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=filters_text,
            reply_markup=await get_filters_keyboard(user_id, page),
        )

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id)


@main_router.callback_query(F.data.startswith("filter_"))
async def handle_filter_selection(callback: types.CallbackQuery):
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

    filters_text = MsgConstants.FILTERS.value

    if user_filters:
        for filter_name in user_filters:
            filters_text += f"• {filter_name}\n"
    else:
        filters_text += "❌ Фильтры не выбраны\n"

    filters_text += "\nПосле выбора нажмите 'Подтвердить'"

    try:
        await callback.message.edit_text(
            text=filters_text, reply_markup=await get_filters_keyboard(user_id, current_page)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=filters_text,
            reply_markup=await get_filters_keyboard(user_id, current_page),
        )

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id)


@main_router.callback_query(F.data == "search_filter")
async def search_filter(callback: types.CallbackQuery, state: FSMContext):
    try:
        await callback.message.edit_text(
            text=MsgConstants.SEARCH_FILTER.value, reply_markup=get_back_to_filters_keyboard()
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id, text=MsgConstants.SEARCH_FILTER.value, reply_markup=get_back_to_filters_keyboard()
        )

    # Устанавливаем состояние ожидания названия фильтра
    await state.set_state(FilterStates.waiting_for_filter_name)
    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id)


@main_router.message(FilterStates.waiting_for_filter_name)
async def process_filter_search(message: types.Message, state: FSMContext):
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
            reply_markup=await get_filters_keyboard(user_id, filter_page),  # Переходим на страницу фильтра
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
            reply_markup=await get_filters_keyboard(user_id, 0),
        )

    # Сбрасываем состояние
    await state.clear()

    # Удаляем сообщение пользователя
    await delete_user_message(message)

    # Обновляем время последней активности
    await db_service.update_user_activity(message.from_user.id)


@main_router.callback_query(F.data == "confirm_filters")
async def confirm_filters(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_filters = await db_service.get_user_filters(user_id)

    # Показываем сообщение о процессе подбора
    processing_message_id = await update_or_send_message(callback.message.chat.id, MsgConstants.PROCESSING.value)

    await db_service.create_user_places_table(user_id)

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

        await update_or_send_message(chat_id=chat_id, text=confirmation_text, reply_markup=get_view_places_keyboard())

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "confirm_filters")


@main_router.callback_query(F.data == "show_geolocation_main")
async def show_geolocation_main(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = await db_service.get_user(user_id)

    geo_text = """
    🗺️ <b>Поиск по геолокации</b>

    Отправьте ваше местоположение, чтобы найти места рядом с вами.
    """

    if user and user["latitude"] is not None and user["longitude"] is not None:
        geo_text += f"""
    <b>Текущее местоположение сохранено</b>
    📍 Широта: {user["latitude"]:.6f}
    📍 Долгота: {user["longitude"]:.6f}

    Теперь вы можете смотреть места рядом с вами.
    """
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📍 Смотреть места рядом", callback_data="view_places_main")],
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
        await update_or_send_message(chat_id=chat_id, text=geo_text, reply_markup=keyboard)

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "show_geolocation_main")


@main_router.callback_query(F.data == "request_location")
async def request_location(callback: types.CallbackQuery):
    try:
        await callback.message.edit_text(
            text=MsgConstants.SEND_LOCATION.value,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="show_geolocation_main")]]
            ),
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=MsgConstants.SEND_LOCATION.value,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="↩️ Назад", callback_data="show_geolocation_main")]]
            ),
        )

    await callback.answer()


@main_router.message(F.content_type == "location")
async def handle_location(message: types.Message):
    user_id = message.from_user.id
    latitude = message.location.latitude
    longitude = message.location.longitude

    # Сохраняем геолокацию пользователя
    user = await db_service.get_user(user_id)
    if user:
        await db_service.save_user(
            user_id=user_id,
            categories=user["categories"],
            wishes=user["wishes"],
            filters=user["filters"],
            latitude=latitude,
            longitude=longitude,
        )
    else:
        # Если пользователя нет в базе, создаем запись
        await db_service.save_user(
            user_id=user_id,
            categories=[],
            wishes=[],
            filters=[],
            latitude=latitude,
            longitude=longitude,
        )

    # пересоздаем таблицу мест с новой геолокацией
    await db_service.create_user_places_table(user_id)

    # Отправляем подтверждение

    await update_or_send_message(
        chat_id=message.chat.id,
        text=MsgConstants.GEO_SAVED.value,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📍 Смотреть места рядом", callback_data="view_places_main")],
                [InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")],
            ]
        ),
    )

    # Удаляем сообщение с геолокацией
    await delete_user_message(message)

    # Обновляем время последней активности
    await db_service.update_user_activity(message.from_user.id)


@main_router.callback_query(F.data == "show_help_main")
async def show_help_main(callback: types.CallbackQuery):
    try:
        await callback.message.edit_text(text=MsgConstants.HELP_TEXT.value, reply_markup=get_back_to_main_keyboard())
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id, text=MsgConstants.HELP_TEXT.value, reply_markup=get_back_to_main_keyboard()
        )

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "show_help_main")


# Обработчики инлайн кнопок
@main_router.callback_query(F.data.in_(MsgConstants.CATEGORIES_TYPES.value))
async def handle_category_selection(callback: types.CallbackQuery):
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
            text=MsgConstants.CATEGORIES.value, reply_markup=get_categories_keyboard(user_id)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        # Если не удалось отредактировать, отправляем новое сообщение
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=MsgConstants.CATEGORIES.value,
            reply_markup=get_categories_keyboard(user_id),
        )

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id)


@main_router.callback_query(F.data == "confirm_categories")
async def confirm_categories(callback: types.CallbackQuery):
    try:
        await callback.message.edit_text(
            text=MsgConstants.WISHES.value, reply_markup=get_wishes_keyboard(callback.from_user.id)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=MsgConstants.WISHES.value,
            reply_markup=get_wishes_keyboard(callback.from_user.id),
        )

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "confirm_categories")


@main_router.callback_query(F.data.in_(MsgConstants.WISHES_TYPES.value))
async def handle_wish_selection(callback: types.CallbackQuery):
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
        await callback.message.edit_text(text=MsgConstants.WISHES.value, reply_markup=get_wishes_keyboard(user_id))
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id, text=MsgConstants.WISHES.value, reply_markup=get_wishes_keyboard(user_id)
        )

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id)


@main_router.callback_query(F.data == "confirm_wishes")
async def confirm_wishes(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    user_data = redis_service.get_user_data(user_id)
    categories_count = len(user_data["selected_categories"])
    wishes_count = len(user_data["selected_wishes"])

    # Показываем сообщение о процессе подбора

    processing_message_id = await update_or_send_message(callback.message.chat.id, MsgConstants.PROCESSING.value)

    # Получаем текущие данные пользователя из базы (включая геопозицию)
    user = await db_service.get_user(user_id)

    # Сохраняем пользователя в базу данных с сохранением геопозиции
    await db_service.save_user(
        user_id=user_id,
        categories=list(user_data["selected_categories"]),
        wishes=list(user_data["selected_wishes"]),
        filters=user["filters"] if user else [],  # Сохраняем текущие фильтры
        latitude=user["latitude"] if user else None,  # Сохраняем геопозицию
        longitude=user["longitude"] if user else None,  # Сохраняем геопозицию
    )

    await db_service.create_user_places_table(user_id)

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

        await update_or_send_message(chat_id=chat_id, text=confirmation_text, reply_markup=get_view_places_keyboard())

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "confirm_wishes")


@main_router.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: types.CallbackQuery):
    photo = FSInputFile(START_IMG_PATH)

    chat_id = callback.message.chat.id

    await update_or_send_message(
        chat_id=chat_id, text=MsgConstants.WELCOME.value, reply_markup=get_main_keyboard(), photo_url=photo
    )
    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id, "main_menu")


@main_router.callback_query(F.data.in_(["place_prev", "place_next"]))
async def navigate_places(callback: types.CallbackQuery):
    logger.info("navigate")
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
                await callback.message.edit_text(text=MsgConstants.ALL_VIEWED.value, reply_markup=keyboard)
            except Exception as e:
                logger.error(f"Error editing message: {e}")
                chat_id = callback.message.chat.id
                await update_or_send_message(chat_id=chat_id, text=MsgConstants.ALL_VIEWED.value, reply_markup=keyboard)
            await callback.answer()
            return

    redis_service.set_user_data_params(user_id, {"current_place_index": current_index})

    # Показываем место
    await show_place(user_id, callback.message.chat.id, current_index)

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id)


# Обработчик отмены состояния фильтра
@main_router.callback_query(F.data == "show_filters_main", FilterStates.waiting_for_filter_name)
async def cancel_filter_search(callback: types.CallbackQuery, state: FSMContext):
    logger.info("-----------")
    user_id = callback.from_user.id
    user_filters = await db_service.get_user_filters(user_id)

    filters_text = MsgConstants.FILTERS.value

    if user_filters:
        for filter_name in user_filters:
            filters_text += f"• {filter_name}\n"
    else:
        filters_text += "❌ Фильтры не выбраны\n"

    filters_text += "\nПосле выбора нажмите 'Подтвердить'"

    try:
        await callback.message.edit_text(text=filters_text, reply_markup=await get_filters_keyboard(user_id, 0))
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=filters_text,
            reply_markup=await get_filters_keyboard(user_id, 0),
        )

    # Сбрасываем состояние
    await state.clear()

    await callback.answer()

    # Обновляем время последней активности
    await db_service.update_user_activity(callback.from_user.id)


# Обработчик всех текстовых сообщений (удаление)
@main_router.message()
async def delete_all_messages(message: types.Message):
    await delete_user_message(message)

    # Обновляем время последней активности
    await db_service.update_user_activity(message.from_user.id)


# Запуск бота
# async def main():
#     logging.basicConfig(
#         level=logging.INFO,
#         format="%(asctime)s - %(levelname)s - %(message)s",
#         datefmt="%Y-%m-%d %H:%M:%S",
#     )
#     try:
#         await db_service.init_db(
#             Settings.POSTGRES_USER,
#             Settings.POSTGRES_PASSWORD,
#             Settings.POSTGRES_DB,
#             Settings.POSTGRES_HOST,
#             Settings.POSTGRES_PORT,
#         )
#         await db_service.create_tables()
#         scheduler.add_job(db_service.reset_viewed_by_timer, CronTrigger(hour=4, minute=0))
#         scheduler.add_job(daily_report, CronTrigger(hour=0, minute=0), kwargs={"by_timer": True})
#         scheduler.start()
#         logger.info("Starting single-message bot with database support...")
#         logger.info(f"Планировщик задач:, {scheduler.get_jobs()}")
#         await dp.start_polling(bot)
#     finally:
#         logger.info("Error while starting, closing database...")
#         await db_service.close_db()


# if __name__ == "__main__":
#     asyncio.run(main())
