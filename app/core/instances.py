import pytz
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redis import Redis

from app.core.settings import Settings
from app.repositories.db_repo import DbRepo
from app.repositories.redis_repo import RedisRepo
from app.services.coordinator import Coordinator
from app.services.db_service import DbService
from app.services.redis_service import RedisService

bot = Bot(token=Settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

jobstores = {
    "default": SQLAlchemyJobStore(
        url=(
            f"postgresql+psycopg2://{Settings.POSTGRES_USER}:"
            f"{Settings.POSTGRES_PASSWORD}@"
            f"{Settings.POSTGRES_HOST}:"
            f"{Settings.POSTGRES_PORT}/"
            f"{Settings.POSTGRES_DB}"
        )
    )
}
scheduler = AsyncIOScheduler(jobstores=jobstores, timezone=pytz.timezone("Europe/Moscow"))

db_repo = DbRepo()
db_service = DbService(db_repo)

redis_repo = RedisRepo(
    Redis(Settings.REDIS_HOST, Settings.REDIS_PORT, password=Settings.REDIS_PASSWORD, decode_responses=True)
)
redis_service = RedisService(redis_repo)

coordinator = Coordinator(db_service, redis_service)
