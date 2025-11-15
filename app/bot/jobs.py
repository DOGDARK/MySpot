import logging
from datetime import datetime, timedelta
from typing import Optional

import pytz
from aiogram.exceptions import TelegramForbiddenError
from apscheduler.triggers.date import DateTrigger

from app.bot.admin_keyboards import get_menu_keyboard
from app.bot.constants import Constants
from app.core.instances import bot, db_service, redis_service, scheduler

logger = logging.getLogger(__name__)


def reset_daily_count() -> None:
    redis_service.set_daily_count(0)


async def notify_users(
    msg_text: str,
    users_ids: list[int],
    photo_id: Optional[int] = None,
) -> None:
    pass
    del_count = 0
    for user_id in users_ids:
        try:
            msg_id = None
            if photo_id:
                sent_msg = await bot.send_photo(
                    chat_id=user_id, photo=photo_id, caption=msg_text, reply_markup=get_menu_keyboard()
                )

            else:
                sent_msg = await bot.send_message(chat_id=user_id, text=msg_text, reply_markup=get_menu_keyboard())

            msg_id = sent_msg.message_id
            trigger_time = datetime.now(pytz.timezone("Europe/Moscow")) + timedelta(hours=12)
            scheduler.add_job(
                delete_notify_msg,
                trigger=DateTrigger(run_date=trigger_time),
                misfire_grace_time=300,
                args=(user_id, msg_id),
            )
            logger.info(
                f"Notification sent to {user_id=} and will be deleted at {trigger_time.strftime('%Y-%m-%d %H:%M:%S %Z')}"
            )

        except TelegramForbiddenError as e:
            logger.info(f"{e}")
            await db_service.delete_user(user_id)
            del_count += 1
        except Exception as e:
            logger.error(f"Error sending notification: {e}")

    logger.info(f"All users notified. Deleted: {del_count=}")

    text_part = "пользователей заблокировали"
    if del_count % 10 == 1:
        text_part = "пользователь заблокировал"
    elif del_count % 10 in range(2, 5):
        text_part = "пользователя заблокировали"

    for admin_id in Constants.ADMIN_IDS.value:
        try:
            await bot.send_message(
                admin_id, f"Рассылка доставлена.\n{del_count} {text_part} бота и были удалены из базы."
            )
        except Exception as e:
            logger.error(f"Error while notifying admins: {e}")


async def delete_notify_msg(chat_id: int, msg_id: int) -> None:
    await bot.delete_message(chat_id=chat_id, message_id=msg_id)
