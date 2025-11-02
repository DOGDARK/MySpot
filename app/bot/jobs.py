import logging
from typing import Optional

from app.bot.admin_keyboards import get_menu_keyboard
from app.core.instances import bot, redis_service

logger = logging.getLogger(__name__)


async def notify_users(
    msg_text: str,
    users_ids: list[int],
    photo_id: Optional[int] = None,
) -> None:
    pass
    for user_id in users_ids:
        try:
            if photo_id:
                await bot.send_photo(
                    chat_id=user_id, photo=photo_id, caption=msg_text, reply_markup=get_menu_keyboard()
                )
            else:
                await bot.send_message(chat_id=user_id, text=msg_text, reply_markup=get_menu_keyboard())
            logger.info(f"Notification sent to {user_id=}")
        except Exception as e:
            logger.error(f"Error sending notification: {e}")


def reset_daily_count() -> None:
    redis_service.set_daily_count(0)
