import logging
from math import atan2, cos, radians, sin, sqrt
from typing import Any, Optional

from aiogram import Bot, types
from aiogram.types import InlineKeyboardMarkup, FSInputFile

from app.bot.base_keyboards import get_places_keyboard
from app.services import redis_service
from app.services.db_service import DbService
from app.services.redis_service import RedisService

logger = logging.getLogger(__name__)


# Функции для работы с сообщениями
async def delete_user_message(message: types.Message):
    """Удалить сообщение пользователя"""
    try:
        await message.delete()
    except Exception as e:
        logger.error(f"Error while deleting user msg, {e}")


async def update_or_send_message(
    chat_id: int, text: str, bot: Bot, redis_service: RedisService, reply_markup=None, photo_url: str = None, gif: str = None
):
    """Обновить существующее сообщение или отправить новое"""
    last_msg = redis_service.get_user_msg(chat_id)
    if last_msg:
        try:
            if gif:
                message = await bot.send_animation(
                    chat_id=chat_id,
                    animation=gif,
                    caption=text,
                    reply_markup=reply_markup,
                )
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=last_msg)
                except Exception as e:
                    logger.error(f"Error while deleting user msg, {e}")
            elif photo_url:
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
            if gif:
                message = await bot.send_animation(
                    chat_id=chat_id,
                    animation=gif,
                    caption=text,
                    reply_markup=reply_markup,
                )
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=last_msg)
                except Exception as e:
                    logger.error(f"Error while deleting user msg, {e}")
            elif photo_url:
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


async def show_place(
    user_id: int, chat_id: int, index: int, bot: Bot, db_service: DbService, redis_service: redis_service
):
    places = redis_service.get_user_data(user_id).get("places", [])

    if not places or index >= len(places):
        return

    place = places[index]

    # Формируем текст с рейтингом
    rating = place.get("rating")
    rating_text = f"⭐ {rating}/5" if rating else "⭐ Рейтинг не указан"

    # Получаем категории и пожелания места из базы данных и ормируем текст с категориями и пожеланиями
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
    place_text = generate_place_text(place, website, rating_text, distance_text)

    # Получаем ссылку на фото и проверяем ее валидность
    photo_url = place.get("photo")

    # Проверяем, является ли photo_url валидной ссылкой
    if photo_url and isinstance(photo_url, str) and photo_url.startswith(("http://", "https://")):
        try:
            await update_or_send_message(
                chat_id=chat_id,
                text=place_text,
                bot=bot,
                redis_service=redis_service,
                reply_markup=get_places_keyboard(),
                photo_url=photo_url,
            )
        except Exception as e:
            logger.error(f"Error sending photo message: {e}")
            # Если не удалось отправить с фото, отправляем без фото
            await update_or_send_message(
                chat_id=chat_id,
                text=place_text,
                bot=bot,
                redis_service=redis_service,
                reply_markup=get_places_keyboard(),
            )
    else:
        # Если фото нет или ссылка невалидна, отправляем без фото
        await update_or_send_message(
            chat_id=chat_id, text=place_text, bot=bot, redis_service=redis_service, reply_markup=get_places_keyboard()
        )
    # Помечаем место как просмотренное по названию
    await db_service.mark_place_as_viewed(user_id, place.get("name"))


def generate_place_text(
    place: dict[Any, Any],
    website: str,
    rating_text: str,
    distance_text: str | None = None,
    categories_text: str | None = None,
    wishes_text: str | None = None,
) -> str:
    place_name = (
        f"<a href='{website}'>{place.get('name', 'Не указано')}</a>" if website else place.get("name", "Не указано")
    )
    rating = rating_text + distance_text if distance_text else rating_text
    if categories_text and wishes_text:
        return f"""
<b>Название места:</b> {place_name}
<b>Фильтры:</b> {place.get("categories", "Не указаны")}
<b>Категории:</b> {categories_text}
<b>Пожелания:</b> {wishes_text}
<b>Рейтинг:</b> {rating}
<b>Описание:</b> {place.get("description", "Описание отсутствует")}
<b>Адрес:</b> {place.get("address", "Адрес не указан")}
    """
    else:
        return f"""
<b>Название места:</b> {place_name}
<b>Фильтры:</b> {place.get("categories", "Не указаны")}
<b>Рейтинг:</b> {rating}
<b>Описание:</b> {place.get("description", "Описание отсутствует")}
<b>Адрес:</b> {place.get("address", "Адрес не указан")}
        """


async def notify_users(
    bot: Bot,
    msg_text: str,
    users_ids: list[int],
    photo_id: Optional[int] = None,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    pass
    for user_id in users_ids:
        if photo_id:
            await bot.send_photo(chat_id=user_id, photo=photo_id, caption=msg_text, reply_markup=reply_markup)
        else:
            await bot.send_message(chat_id=user_id, text=msg_text, reply_markup=reply_markup)
