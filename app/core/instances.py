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


class Factory:
    _instance = None

    def __init__(self):
        self._settings = Settings()
        self._singleton = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_bot(self):
        if not self._singleton.get("bot"):
            self._singleton["bot"] = Bot(
                token=self._settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)
            )
        return self._singleton["bot"]

    def get_dp(self):
        if not self._singleton.get("dp"):
            self._singleton["dp"] = Dispatcher()
        return self._singleton["dp"]

    def get_scheduler(self):
        if not self._singleton.get("sch"):
            self._singleton["sch"] = AsyncIOScheduler(timezone=pytz.timezone("Europe/Moscow"))
        return self._singleton["sch"]

    def get_db_service(self):
        if not self._singleton.get("db_serv"):
            db_repo = DbRepo()
            self._singleton["db_serv"] = DbService(db_repo)
        return self._singleton["db_serv"]

    def get_redis_service(self):
        if not self._singleton.get("redis_serv"):
            redis_repo = RedisRepo(Redis(Settings.REDIS_HOST, Settings.REDIS_PORT, decode_responses=True))
            self._singleton["redis_serv"] = DbService(redis_repo)
        return self._singleton["redis_serv"]

    # dp = Dispatcher()
    # scheduler = AsyncIOScheduler(timezone=pytz.timezone("Europe/Moscow"))

    # db_repo = DbRepo()
    # db_service = DbService(db_repo)

    # redis_repo = RedisRepo(Redis(Settings.REDIS_HOST, Settings.REDIS_PORT, decode_responses=True))
    # redis_service = RedisService(redis_repo)
