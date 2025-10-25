import pytz
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redis import Redis

from app.core.settings import Settings
from app.repositories.db_repo import DbRepo
from app.repositories.redis_repo import RedisRepo
from app.services.db_service import DbService
from app.services.redis_service import RedisService

bot = Bot(token=Settings.BOT_TOKEN, parse_mode=ParseMode.HTML, bot=DefaultBotProperties())
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=pytz.timezone("Europe/Moscow"))

db_repo = DbRepo()
db_service = DbService(db_repo)

redis_repo = RedisRepo(Redis(Settings.REDIS_HOST, Settings.REDIS_PORT, decode_responses=True))
redis_service = RedisService(redis_repo)
