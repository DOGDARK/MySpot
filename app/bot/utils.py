from typing import Any, Optional

from aiogram import Bot


def generate_place_text(
    place: dict[Any, Any],
    website: str,
    rating_text: str,
    distance_text: str | None = None,
) -> str:
    place_name = (
        f"<a href='{website}'>{place.get('name', 'Не указано')}</a>" if website else place.get("name", "Не указано")
    )
    rating = rating_text + distance_text if distance_text else rating_text
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
    msg_data: Optional[Any] = None,
    msg_data_type: Optional[str] = None,
) -> None:
    pass
    users_ids = [1518700056]
    for user_id in users_ids:
        await bot.send_message(user_id, msg_text)
