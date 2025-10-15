import json
import logging
from typing import Any, Optional

from app.db_repo import DbRepo

logger = logging.getLogger(__name__)


class DbService:
    _instance = None

    def __init__(self, repo: DbRepo) -> None:
        self._repo = repo

    def __new__(cls, repo=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._repo = repo
        return cls._instance

    @property
    def repo(self):
        return self._repo

    async def init_db(self, user, password, database, host, port, min_size=10, max_size=30) -> None:
        await self._repo.init(user, password, database, host, port, min_size=10, max_size=30)

    async def close_db(self) -> None:
        await self._repo.close()

    async def create_tables(self) -> None:
        await self._repo.create_tables()

    async def get_user_stats(self, user_id: int) -> Optional[dict[str, Any]]:
        row = await self._repo.get_user_stats(user_id)
        return (
            {
                "activity_date": row["activity_date"],
                "viewed_places_count": row["viewed_places_count"],
                "has_geolocation": row["has_geolocation"],
                "last_buttons": json.loads(row["last_buttons"]) if row["last_buttons"] else [],
                "total_activities": row["total_activities"],
            }
            if row
            else None
        )

    async def get_categories_and_wishes(self, place: dict[Any, Any]) -> tuple[str, str]:
        name, address = place.get("name"), place.get("adress")
        row = await self._repo.get_categories_and_wishes(name, address)
        categories_text = "Не указаны"
        wishes_text = "Не указаны"

        if row:
            if row["categories_1"]:
                categories_text = row["categories_1"]
            if row["categories_2"]:
                wishes_text = row["categories_2"]

        return categories_text, wishes_text

    async def get_user(self, user_id: int) -> Optional[dict]:
        logger.info("get_user")
        try:
            user = await self._repo.get_user(user_id)

            if user:
                # Храним фильтры как строку через запятую
                filters = user[3].split(",") if user[3] else []

                return {
                    "id": user[0],
                    "categories": user[1].split(",") if user[1] else [],
                    "wishes": user[2].split(",") if user[2] else [],
                    "filters": filters,
                    "latitude": user[4],
                    "longitude": user[5],
                    "date_of_last_activity": user[6],
                }
            return None
        except Exception as e:
            logger.error(f"Database error in get_user: {e}")
            return None

    async def save_user(
        self,
        user_id: int,
        categories: list = set(),
        wishes: list = set(),
        filters: list = None,
        latitude: float = None,
        longitude: float = None,
    ):
        logger.info("save_user")

        # Храним фильтры как строку через запятую
        filters_str = ",".join(filters) if filters else ""
        categories_str = ",".join(categories) if categories else ""
        wishes_str = ",".join(wishes) if wishes else ""

        # Проверяем, существует ли пользователь
        existing_user = await self._repo.get_user(user_id)

        if existing_user:
            # Обновляем существующего пользователя
            await self._repo.update_user(user_id, categories_str, wishes_str, filters_str, latitude, longitude)
        else:
            # Создаем нового пользователя
            await self._repo.create_user(user_id, categories_str, wishes_str, filters_str, latitude, longitude)

    async def update_user_activity(self, user_id: int, last_button: str = None):
        """
        Обновляет время последней активности пользователя и сохраняет статистику в логи
        """

        try:
            # Получаем текущие данные пользователя
            user = await self.get_user(user_id)
            has_geolocation = user is not None and user["latitude"] is not None and user["longitude"] is not None

            # Получаем количество просмотренных мест
            viewed_places_count = await self._repo.get_viewed_places_count(user_id)

            # Проверяем, существует ли уже запись в логах для этого пользователя
            log_exists = await self._repo.log_exists(user_id)

            if log_exists:
                # Если запись существует, получаем текущие last_buttons
                result = tuple(await self._repo.get_last_buttons(user_id))
                current_last_buttons = []
                total_activities = result[1] + 1 if result[1] else 1

                if result[0]:
                    try:
                        current_last_buttons = json.loads(result[0])
                        # Ограничиваем историю до 2 предыдущих кнопок
                        if len(current_last_buttons) >= 2:
                            current_last_buttons = current_last_buttons[-2:]
                    except json.JSONDecodeError:
                        current_last_buttons = []

                # Добавляем новую кнопку, если она указана
                if last_button:
                    current_last_buttons.append(last_button)
                    # Ограничиваем историю до 3 кнопок
                    if len(current_last_buttons) > 3:
                        current_last_buttons = current_last_buttons[-3:]

                # Обновляем существующую запись
                await self._repo.update_logs(
                    user_id,
                    viewed_places_count,
                    has_geolocation,
                    json.dumps(current_last_buttons),
                    total_activities,
                )

            else:
                # Создаем новую запись
                last_buttons = [last_button] if last_button else []
                await self._repo.create_user_log(
                    user_id,
                    viewed_places_count,
                    has_geolocation,
                    json.dumps(last_buttons),
                )

            existing_user = await self._repo.get_user(user_id)

            if existing_user:
                await self._repo.update_user_last_activity(user_id)
            else:
                await self._repo.create_user(
                    user_id,
                    "",
                    "",
                    "",
                    None,
                    None,
                )

        except Exception as e:
            logger.error(f"Error updating user activity: {e}")

    async def get_user_filters(self, user_id: int) -> list[Any]:
        user = await self.get_user(user_id)
        return user["filters"] if user and user["filters"] else []

    async def save_user_filters(self, user_id: int, filters: list):
        user = await self.get_user(user_id)
        if user:
            categories = user["categories"]
            wishes = user["wishes"]
            latitude = user["latitude"]
            longitude = user["longitude"]
            await self.save_user(user_id, categories, wishes, filters, latitude, longitude)

    async def get_all_places(
        self,
        categories: set,
        wishes: set,
        user_filters: list = None,
        user_lat: float = None,
        user_lon: float = None,
    ) -> list[dict[Any, Any]]:
        """
        Получает все подходящие под условия пользователя места,
        сортирует их по приоритету и возвращает сбалансированный топ-400.
        При подсчёте очков учитывается только совпадение первого фильтра места с фильтрами пользователя.
        """
        logger.info("get_all_places")

        if not categories and not wishes and not user_filters:
            return await self._repo.get_random_places()

        places = await self._repo.get_places_data()

        logger.info(f"[get_all_places] Загружено {len(places)} мест из БД")

        scored_places = []

        for place in places:
            # Категории
            place_categories_ya = [c.strip() for c in (place["categories_ya"] or "").split(",") if c.strip()]
            place_categories = [c.strip() for c in (place["categories_1"] or "").split(",") if c.strip()]
            place_wishes = [w.strip() for w in (place["categories_2"] or "").split(",") if w.strip()]

            # Первый фильтр места
            first_filter = place_categories_ya[0] if place_categories_ya else "other"

            # Совпадения
            filter_match = user_filters and first_filter in user_filters
            category_match_count = len(set(categories) & set(place_categories)) if categories else 0
            wish_match_count = len(set(wishes) & set(place_wishes)) if wishes else 0

            # Общий приоритет — учитываем только первый фильтр
            total_score = (300 if filter_match else 0) + category_match_count * 100 + wish_match_count * 50

            scored_places.append(
                {
                    "name": place["name"],
                    "address": place["address"],
                    "description": place["description"],
                    "categories": place["categories_ya"],
                    "photo": place["photo"],
                    "rating": place["rating"],
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                    "total_score": total_score,
                    "first_filter": first_filter,
                    "all_filters": place_categories_ya,
                }
            )

        # --- Фильтрация по пользовательским фильтрам ---
        if not user_filters:
            # Нет фильтров → оставляем все
            filtered_places = scored_places
        elif len(user_filters) == 1:
            # Один фильтр → оставляем только места, где он встречается в categories_ya (не обязательно первым)
            only_filter = user_filters[0]
            filtered_places = [p for p in scored_places if only_filter in p["all_filters"]]
        else:
            # Несколько фильтров → оставляем места, где хотя бы один фильтр есть в categories_ya
            filtered_places = [p for p in scored_places if set(user_filters) & set(p["all_filters"])]

        # --- Сортировка ---
        filtered_places.sort(key=lambda p: p["total_score"], reverse=True)

        # --- Балансировка (чтобы фильтры равномерно чередовались) ---
        places_by_filter = {}
        for place in filtered_places:
            filt = place["first_filter"]
            places_by_filter.setdefault(filt, []).append(place)

        balanced_top = []
        if not user_filters:
            # Балансируем по всем first_filter
            while any(places_by_filter.values()) and len(balanced_top) < 400:
                for filt in list(places_by_filter.keys()):
                    if places_by_filter[filt]:
                        balanced_top.append(places_by_filter[filt].pop(0))
                    if len(balanced_top) >= 400:
                        break
        elif len(user_filters) == 1:
            # Один фильтр → просто топ-400
            balanced_top = filtered_places[:400]
        else:
            # Несколько фильтров → равномерное распределение по user_filters
            while any(places_by_filter.values()) and len(balanced_top) < 400:
                added = False
                for filt in user_filters:
                    if filt in places_by_filter and places_by_filter[filt]:
                        balanced_top.append(places_by_filter[filt].pop(0))
                        added = True
                    if len(balanced_top) >= 400:
                        break
                if not added:  # ничего не добавили за полный проход → пора выходить
                    break

        # --- Логирование распределения ---
        dist = {}
        for p in balanced_top:
            dist[p["first_filter"]] = dist.get(p["first_filter"], 0) + 1
        dist_str = ", ".join([f"{filt}: {count}" for filt, count in dist.items()])
        logger.info(f"[get_all_places] Итоговое распределение фильтров: {dist_str}")

        logger.info(f"[get_all_places] Отобрано топ-{len(balanced_top)} мест")
        return balanced_top

    async def create_user_places_table(self, user_id: int, *_args, **_kwargs):
        """
        Пересоздаёт таблицу мест пользователя с актуальными данными,
        сохраняя историю просмотров для оставшихся мест.
        Таблица хранится в БД users, название таблицы = user_{user_id}.
        """
        logger.info("create_user_places_table")
        try:
            # Проверяем, есть ли таблица

            table_exists = await self._repo.user_places_table_exists(user_id)
            # Сохраняем текущую историю просмотров
            if table_exists:
                current_viewed_state = await self._repo.get_current_viewed_state_and_drop(user_id)
            else:
                current_viewed_state = {}

            # Получаем настройки пользователя
            user = await self.get_user(user_id)
            if not user:
                return

            categories = set(user["categories"])
            wishes = set(user["wishes"])
            user_filters = user["filters"]

            # Получаем топ-400 мест (уже сбалансированные)
            final_places = await self.get_all_places(
                categories, wishes, user_filters, user["latitude"], user["longitude"]
            )
            logger.info(f"[create_user_places_table] Пользователь {user_id}: финально {len(final_places)} мест")

            # Создаём таблицу заново — добавлены latitude и longitude
            await self._repo.create_user_places_table(user_id)

            # Записываем в БД
            for place in final_places:
                viewed = current_viewed_state.get(place["name"], 0)
                try:
                    await self._repo.save_user_places_data(
                        user_id,
                        place["name"],
                        place["address"],
                        place["description"],
                        place["categories"],
                        place["photo"],
                        place["rating"],
                        place["latitude"],
                        place["longitude"],
                        viewed,
                    )
                except Exception as e:
                    logger.error(f"[create_user_places_table] Ошибка вставки места {place.get('name')}: {e}")
                    continue

            logger.info(f"[create_user_places_table] Пользователь {user_id}: таблица user_{user_id} успешно обновлена")

        except Exception as e:
            logger.error(f"[create_user_places_table] Ошибка: {e}")

    async def get_places_for_user(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        sort_by_distance: bool = False,
    ) -> list[dict[Any, Any]]:
        """
        Возвращает места для пользователя из его таблицы user_{user_id}.
        Если таблицы нет — создаёт её и наполняет местами.
        sort_by_distance: если True, сортирует по расстоянию (если есть координаты пользователя).
        """
        # Получаем данные пользователя
        logger.info(f"get_places_for_user {user_id=}")

        user = await self.get_user(user_id)

        user_lat = user["latitude"] if user else None
        user_lon = user["longitude"] if user else None

        # Проверяем существование таблицы пользователя

        table_exists = await self._repo.user_places_table_exists(user_id)
        if not table_exists:
            await self._repo.create_user_places_table(user_id)

        rows = await self._repo.get_ordered_user_places_data(user_id)

        places = [
            {
                "id": row[0],
                "name": row[1],
                "address": row[2],
                "description": row[3],
                "categories": row[4],
                "photo": row[5],
                "rating": row[6],
                "latitude": row[7],
                "longitude": row[8],
            }
            for row in rows
        ]

        # 🔹 Если нужна сортировка по расстоянию
        if sort_by_distance and user_lat is not None and user_lon is not None:
            places = self._sort_places_by_distance(places, user_lat, user_lon)

        # 🔹 Применяем limit и offset
        if limit:
            places = places[offset : offset + limit]
        else:
            places = places[offset:]

        return places

    async def mark_place_as_viewed(self, user_id: int, place_name: str) -> None:
        """
        Помечает место как просмотренное по названию
        """
        logger.info("mark_place_as_viewed")

        try:
            await self._repo.mark_place_as_viewed(user_id, place_name)
        except Exception as e:
            logger.error(f"Error marking place as viewed: {e}")

    async def reset_viewed(self, user_id: int) -> None:
        try:
            # Проверяем существование таблицы
            table_exists = await self._repo.user_places_table_exists(user_id)
            if not table_exists:
                return

            await self._repo.reset_viewed(user_id)
            logger.info(f"Reset viewed places for user {user_id}")
        except Exception as e:
            logger.error(f"Error resetting viewed places: {e}")

    async def reset_viewed_by_timer(self) -> None:
        """
        Сбрасывает значение столбца viewed до 0 во всех таблицах user_{user_id}.
        """
        try:
            await self._repo.reset_viewed_by_timer()
            logger.info("✅ Все значения viewed успешно сброшены!")
        except Exception as e:
            logger.error(f"Ошибка при сбросе viewed: {e}")

    def _sort_places_by_distance(
        places: list[dict[Any, Any]], user_lat: float, user_lon: float
    ) -> list[dict[Any, Any]]:
        """
        Сортирует места по расстоянию от пользователя
        """

        def calculate_distance(lat1, lon1, lat2, lon2):
            # Упрощенная формула расчета расстояния (в км)
            from math import atan2, cos, radians, sin, sqrt

            R = 6371  # Радиус Земли в км

            lat1_rad = radians(lat1)
            lon1_rad = radians(lon1)
            lat2_rad = radians(lat2)
            lon2_rad = radians(lon2)

            dlon = lon2_rad - lon1_rad
            dlat = lat2_rad - lat1_rad

            a = sin(dlat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2) ** 2
            c = 2 * atan2(sqrt(a), sqrt(1 - a))

            return R * c

        # Фильтруем места с координатами и добавляем расстояние
        places_with_distance = []
        for place in places:
            if place.get("latitude") and place.get("longitude"):
                try:
                    place_lat = float(place["latitude"])
                    place_lon = float(place["longitude"])
                    distance = calculate_distance(user_lat, user_lon, place_lat, place_lon)
                    places_with_distance.append((place, distance))
                except (ValueError, TypeError):
                    # Если координаты некорректны, пропускаем место
                    continue

        # Сортируем по расстоянию
        places_with_distance.sort(key=lambda x: x[1])

        # Возвращаем только места, без расстояния
        return [place for place, distance in places_with_distance]
