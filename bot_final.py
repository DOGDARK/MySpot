import asyncio
import logging
import sqlite3
import json
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from typing import Dict, List, Optional
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8295800638:AAEyodgPbWEbCn5L0CFdMmDv1f2FN1hf2DM"
MODERATORS_CHAT_ID = -4821742989

# Инициализация бота
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Состояния FSM
class FilterStates(StatesGroup):
    waiting_for_filter_name = State()

# Хранилище данных пользователей
user_data: Dict[int, Dict] = {}
user_messages: Dict[int, int] = {}

# Список доступных фильтров (категорий)
AVAILABLE_FILTERS = [
    "Кафе", "Ресторан", "Кофейня", "Бар", "Пиццерия", "Суши-бар", "Столовая", "Паб", 
    "Чай с собой", "Парк культуры и отдыха", "Кинотеатр", "Театр", "Концертный зал", 
    "Музей", "Художественная галерея", "Выставка", "Выставочный центр", "Культурный центр", 
    "Библиотека", "Планетарий", "Океанариум", "Аквапарк", "Бассейн", "Каток", 
    "Спортивный комплекс", "Спортивный клуб", "Фитнес-центр", "Спортивная школа", 
    "Скалодром", "Боулинг-клуб", "Квесты", "Клуб виртуальной реальности", "Лазертаг", 
    "Пейнтбол", "Картинг", "Батутный центр", "Верёвочный парк", "Аттракцион", 
    "Парк аттракционов", "Детская площадка", "Игровая комната", 
    "Клуб для детей и подростков", "Центр развития ребёнка", "Детский лагерь отдыха", 
    "Организация и проведение детских праздников", "Ночной клуб", "Караоке-клуб", 
    "Караоке-кабинка", "Кальян-бар", "Стриптиз-клуб", "Банкетный зал", "Кейтеринг", 
    "Аренда площадок для культурно-массовых мероприятий", "Антикафе", 
    "Водные прогулки", "Пляж", "Сауна", 
    "Часовня", "Смотровая площадка", "Сквер", "Сад", "Лесопарк", "Заповедник", 
    "Место для пикника", "Алкогольные напитки", "Рюмочная", "Пивоварня", 
    "Пивоваренный завод", "Сыроварня", "Торговый центр", "Игорное и развлекательное оборудование", 
    "Бильярдный клуб", "Игровые приставки", "Компьютерный клуб", "Киберспорт", 
    "Настольные и интеллектуальные игры", "Театрально-концертная касса", 
    "Концертные и театральные агентства", "Горная вершина", "Обсерватория", 
    "Аэроклуб", "Аэротруба", "Центр экстремальных видов спорта", "Зимние развлечения", 
    "Ретритный центр", "Декоративный объект", "Чайная", "Безалкогольный бар", 
    "Скейт-парк", "Танцплощадка", "Оркестр", "Тир", "Лодочная станция", "Водная база"
]



# Подключение к базе данных мест
def get_places_db_connection():
    conn = sqlite3.connect('tg_bot_data_main_corrected_12482_2.db')
    conn.row_factory = sqlite3.Row
    return conn

# Подключение к базе данных пользователей
def get_users_db_connection():
    conn = sqlite3.connect('users.db')
    return conn

# Инициализация базы данных пользователей
def init_users_db():
    conn = get_users_db_connection()
    cursor = conn.cursor()
    
    # Создание таблицы пользователей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        categories TEXT,
        wishes TEXT,
        filters TEXT,
        latitude REAL,
        longitude REAL,
        date_of_last_activity TIMESTAMP
    )
    ''')
    
    # Создание таблицы логов (по одной строке на пользователя)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS logs (
        user_id INTEGER PRIMARY KEY,
        activity_date TIMESTAMP,
        viewed_places_count INTEGER DEFAULT 0,
        has_geolocation BOOLEAN DEFAULT FALSE,
        last_buttons TEXT,
        total_activities INTEGER DEFAULT 1,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    conn.commit()
    conn.close()

# Инициализация базы данных при запуске
init_users_db()


def get_user_stats(user_id: int) -> Optional[dict]:
    """
    Получает статистику пользователя из таблицы logs
    """
    conn = get_users_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        SELECT activity_date, viewed_places_count, has_geolocation, last_buttons, total_activities
        FROM logs WHERE user_id = ?
        ''', (user_id,))
        
        result = cursor.fetchone()
        if result:
            return {
                'activity_date': result[0],
                'viewed_places_count': result[1],
                'has_geolocation': bool(result[2]),
                'last_buttons': json.loads(result[3]) if result[3] else [],
                'total_activities': result[4]
            }
        return None
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        return None
    finally:
        conn.close()

# отправка места на модерацию
@dp.callback_query(F.data == "place_bad")
async def process_place_bad(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id

    places = user_data[user_id].get('places', [])
    index = user_data[user_id].get('current_place_index', 0)

    if not places or index >= len(places):
        await callback_query.answer("Ошибка: не удалось найти место для отправки.", show_alert=True)
        return

    place = places[index]

    # Формируем текст с рейтингом
    rating = place.get('rating')
    rating_text = f"⭐ {rating}/5" if rating else "⭐ Рейтинг не указан"

    # Получаем категории и пожелания места из базы данных
    conn = get_places_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT categories_1, categories_2 FROM places WHERE name = ? AND address = ?',
        (place.get('name'), place.get('address'))
    )
    place_details = cursor.fetchone()
    conn.close()

    categories_text = "Не указаны"
    wishes_text = "Не указаны"

    if place_details:
        if place_details['categories_1']:
            categories_text = place_details['categories_1']
        if place_details['categories_2']:
            wishes_text = place_details['categories_2']

    # Формируем текст
    place_text = f"""
<b>Название места:</b> {place.get('name', 'Не указано')}
<b>Фильтры:</b> {place.get('categories', 'Не указаны')}
<b>Категории:</b> {categories_text}
<b>Пожелания:</b> {wishes_text}
<b>Рейтинг:</b> {rating_text}
<b>Описание:</b> {place.get('description', 'Описание отсутствует')}
<b>Адрес:</b> {place.get('address', 'Адрес не указан')}
    """

    photo_url = place.get('photo')

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
                    parse_mode="HTML"
                )
            else:
                # Если текст слишком длинный
                await callback_query.bot.send_photo(
                    chat_id=MODERATORS_CHAT_ID,
                    photo=photo_url
                )
                await callback_query.bot.send_message(
                    chat_id=MODERATORS_CHAT_ID,
                    text=place_text,
                    parse_mode="HTML"
                )
        else:
            await callback_query.bot.send_message(
                chat_id=MODERATORS_CHAT_ID,
                text=place_text,
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Ошибка отправки в чат модерации: {e}")
        await callback_query.bot.send_message(
            chat_id=MODERATORS_CHAT_ID,
            text=place_text,
            parse_mode="HTML"
        )

    # Помечаем место как просмотренное
    mark_place_as_viewed(user_id, place.get('name'))






# Функции для работы с пользователями

# получение данных пользователя
def get_user(user_id: int) -> Optional[dict]:
    print('get_user')
    try:
        conn = get_users_db_connection()
        cursor = conn.cursor()
        
        # Проверяем существование таблицы users
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        table_exists = cursor.fetchone()
        
        if not table_exists:
            conn.close()
            return
        
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        
        conn.close()
        
        if user:
            # Храним фильтры как строку через запятую
            filters = user[3].split(',') if user[3] else []
            
            return {
                'id': user[0],
                'categories': user[1].split(',') if user[1] else [],
                'wishes': user[2].split(',') if user[2] else [],
                'filters': filters,
                'latitude': user[4],
                'longitude': user[5],
                'date_of_last_activity': user[6]
            }
        return None
    except sqlite3.Error as e:
        logger.error(f"Database error in get_user: {e}")
        return None

# сохранение пользователя
def save_user(user_id: int, categories: list = set(), wishes: list = set(), filters: list = None,
              latitude: float = None, longitude: float = None):
    print('save_user')
    conn = get_users_db_connection()
    cursor = conn.cursor()
    
    # Проверяем, существует ли пользователь
    cursor.execute('SELECT id FROM users WHERE id = ?', (user_id,))
    existing_user = cursor.fetchone()
    
    # Храним фильтры как строку через запятую
    filters_str = ','.join(filters) if filters else ''
    categories_str = ','.join(categories) if categories else ''
    wishes_str = ','.join(wishes) if wishes else ''
    
    if existing_user:
        # Обновляем существующего пользователя
        cursor.execute('''
        UPDATE users 
        SET categories = ?, wishes = ?, filters = ?, latitude = ?, longitude = ?, date_of_last_activity = ?
        WHERE id = ?
        ''', (categories_str, wishes_str, filters_str, latitude, longitude, datetime.now(), user_id))
    else:
        # Создаем нового пользователя
        cursor.execute('''
        INSERT INTO users (id, categories, wishes, filters, latitude, longitude, date_of_last_activity)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, categories_str, wishes_str, filters_str, latitude, longitude, datetime.now()))
    
    conn.commit()
    conn.close()


def update_user_activity(user_id: int, last_button: str = None):
    """
    Обновляет время последней активности пользователя и сохраняет статистику в логи
    """
    conn = get_users_db_connection()
    cursor = conn.cursor()
    
    try:
        # Получаем текущие данные пользователя
        user = get_user(user_id)
        has_geolocation = user and user['latitude'] is not None and user['longitude'] is not None
        
        # Получаем количество просмотренных мест
        viewed_places_count = get_viewed_places_count(user_id)
        
        # Проверяем, существует ли уже запись в логах для этого пользователя
        cursor.execute('SELECT user_id FROM logs WHERE user_id = ?', (user_id,))
        log_exists = cursor.fetchone()
        
        if log_exists:
            # Если запись существует, получаем текущие last_buttons
            cursor.execute('SELECT last_buttons, total_activities FROM logs WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
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
            cursor.execute('''
            UPDATE logs 
            SET activity_date = ?, 
                viewed_places_count = ?, 
                has_geolocation = ?, 
                last_buttons = ?,
                total_activities = ?
            WHERE user_id = ?
            ''', (
                datetime.now(), 
                viewed_places_count, 
                has_geolocation, 
                json.dumps(current_last_buttons),
                total_activities,
                user_id
            ))
        else:
            # Создаем новую запись
            last_buttons = [last_button] if last_button else []
            cursor.execute('''
            INSERT INTO logs (user_id, activity_date, viewed_places_count, has_geolocation, last_buttons, total_activities)
            VALUES (?, ?, ?, ?, ?, 1)
            ''', (user_id, datetime.now(), viewed_places_count, has_geolocation, json.dumps(last_buttons)))
        
        # Обновляем/создаем запись пользователя
        cursor.execute('SELECT id FROM users WHERE id = ?', (user_id,))
        existing_user = cursor.fetchone()
        
        if existing_user:
            cursor.execute('''
            UPDATE users 
            SET date_of_last_activity = ?
            WHERE id = ?
            ''', (datetime.now(), user_id))
        else:
            cursor.execute('''
            INSERT INTO users (id, categories, wishes, filters, latitude, longitude, date_of_last_activity)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, '', '', '', None, None, datetime.now()))
        
        conn.commit()
        
    except Exception as e:
        logger.error(f"Error updating user activity: {e}")
    finally:
        conn.close()


def get_viewed_places_count(user_id: int) -> int:
    """
    Получает количество просмотренных мест пользователя
    """
    conn = get_users_db_connection()
    cursor = conn.cursor()
    
    try:
        # Проверяем существование таблицы пользователя
        cursor.execute(f'''
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='user_{user_id}'
        ''')
        
        table_exists = cursor.fetchone()
        if not table_exists:
            return 0
        
        cursor.execute(f'''
        SELECT COUNT(*) FROM user_{user_id} WHERE viewed = 1
        ''')
        count = cursor.fetchone()[0]
        return count
    except Exception as e:
        logger.error(f"Error getting viewed places count: {e}")
        return 0
    finally:
        conn.close()


# Функции для работы с фильтрами пользователя
def get_user_filters(user_id: int) -> list:
    user = get_user(user_id)
    return user['filters'] if user and 'filters' in user else []


def save_user_filters(user_id: int, filters: list):
    user = get_user(user_id)
    if user:
        categories = user['categories']
        wishes = user['wishes']
        latitude = user['latitude']
        longitude = user['longitude']
        save_user(user_id, categories, wishes, filters, latitude, longitude)

# Функции для работы с местами
def get_all_places(categories: set, wishes: set, user_filters: list = None,
                   user_lat: float = None, user_lon: float = None) -> List[dict]:
    """
    Получает все подходящие под условия пользователя места,
    сортирует их по приоритету и возвращает сбалансированный топ-400.
    При подсчёте очков учитывается только совпадение первого фильтра места с фильтрами пользователя.
    """
    print('get_all_places')
    conn = get_places_db_connection()
    cursor = conn.cursor()

    if not categories and not wishes and not user_filters:
            cursor.execute('''
                SELECT name, address, description, categories_ya As categories, categories_1, categories_2,
                    photo, rating, latitude, longitude
                FROM places
                ORDER BY RANDOM()
                LIMIT 400
            ''')
            places = cursor.fetchall()
            conn.close()
            return places

    cursor.execute('''
        SELECT name, address, description, categories_ya, categories_1, categories_2,
               photo, rating, latitude, longitude
        FROM places
    ''')
    places = cursor.fetchall()
    conn.close()

    logger.info(f"[get_all_places] Загружено {len(places)} мест из БД")

    scored_places = []

    for place in places:
        # Категории
        place_categories_ya = [c.strip() for c in (place['categories_ya'] or '').split(',') if c.strip()]
        place_categories = [c.strip() for c in (place['categories_1'] or '').split(',') if c.strip()]
        place_wishes = [w.strip() for w in (place['categories_2'] or '').split(',') if w.strip()]

        # Первый фильтр места
        first_filter = place_categories_ya[0] if place_categories_ya else "other"

        # Совпадения
        filter_match = user_filters and first_filter in user_filters
        category_match_count = len(set(categories) & set(place_categories)) if categories else 0
        wish_match_count = len(set(wishes) & set(place_wishes)) if wishes else 0

        # Общий приоритет — учитываем только первый фильтр
        total_score = (
            (300 if filter_match else 0) +
            category_match_count * 100 +
            wish_match_count * 50
        )

        scored_places.append({
            'name': place['name'],
            'address': place['address'],
            'description': place['description'],
            'categories': place['categories_ya'],
            'photo': place['photo'],
            'rating': place['rating'],
            'latitude': place['latitude'],
            'longitude': place['longitude'],
            'total_score': total_score,
            'first_filter': first_filter,
            'all_filters': place_categories_ya
        })

    # --- Фильтрация по пользовательским фильтрам ---
    if not user_filters:
        # Нет фильтров → оставляем все
        filtered_places = scored_places
    elif len(user_filters) == 1:
        # Один фильтр → оставляем только места, где он встречается в categories_ya (не обязательно первым)
        only_filter = user_filters[0]
        filtered_places = [p for p in scored_places if only_filter in p['all_filters']]
    else:
        # Несколько фильтров → оставляем места, где хотя бы один фильтр есть в categories_ya
        filtered_places = [p for p in scored_places if set(user_filters) & set(p['all_filters'])]

    # --- Сортировка ---
    filtered_places.sort(key=lambda p: p['total_score'], reverse=True)

    # --- Балансировка (чтобы фильтры равномерно чередовались) ---
    places_by_filter = {}
    for place in filtered_places:
        filt = place['first_filter']
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
        dist[p['first_filter']] = dist.get(p['first_filter'], 0) + 1
    dist_str = ", ".join([f"{filt}: {count}" for filt, count in dist.items()])
    logger.info(f"[get_all_places] Итоговое распределение фильтров: {dist_str}")

    logger.info(f"[get_all_places] Отобрано топ-{len(balanced_top)} мест")
    return balanced_top


def sort_places_by_distance(places: List[dict], user_lat: float, user_lon: float) -> List[dict]:
    """
    Сортирует места по расстоянию от пользователя
    """
    def calculate_distance(lat1, lon1, lat2, lon2):
        # Упрощенная формула расчета расстояния (в км)
        from math import radians, sin, cos, sqrt, atan2
        R = 6371  # Радиус Земли в км
        
        lat1_rad = radians(lat1)
        lon1_rad = radians(lon1)
        lat2_rad = radians(lat2)
        lon2_rad = radians(lon2)
        
        dlon = lon2_rad - lon1_rad
        dlat = lat2_rad - lat1_rad
        
        a = sin(dlat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        return R * c
    
    # Фильтруем места с координатами и добавляем расстояние
    places_with_distance = []
    for place in places:
        if place.get('latitude') and place.get('longitude'):
            try:
                place_lat = float(place['latitude'])
                place_lon = float(place['longitude'])
                distance = calculate_distance(user_lat, user_lon, place_lat, place_lon)
                places_with_distance.append((place, distance))
            except (ValueError, TypeError):
                # Если координаты некорректны, пропускаем место
                continue
    
    # Сортируем по расстоянию
    places_with_distance.sort(key=lambda x: x[1])
    
    # Возвращаем только места, без расстояния
    return [place for place, distance in places_with_distance]


def create_user_places_table(user_id: int, *_args, **_kwargs):
    """
    Пересоздаёт таблицу мест пользователя с актуальными данными,
    сохраняя историю просмотров для оставшихся мест.
    Таблица хранится в БД users, название таблицы = user_{user_id}.
    """
    print('create_user_places_table')
    conn = get_users_db_connection()
    cursor = conn.cursor()
    try:
        table_name = f"user_{user_id}"

        # Проверяем, есть ли таблица
        cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name=?
        """, (table_name,))
        table_exists = cursor.fetchone()

        # Сохраняем текущую историю просмотров
        if table_exists:
            cursor.execute(f"SELECT name, viewed FROM '{table_name}'")
            current_viewed_state = {row[0]: row[1] for row in cursor.fetchall()}
            cursor.execute(f"DROP TABLE '{table_name}'")
        else:
            current_viewed_state = {}

        # Получаем настройки пользователя
        user = get_user(user_id)
        if not user:
            return

        categories = set(user['categories'])
        wishes = set(user['wishes'])
        user_filters = user['filters']

        # Получаем топ-400 мест (уже сбалансированные)
        final_places = get_all_places(categories, wishes, user_filters, user['latitude'], user['longitude'])
        logger.info(f"[create_user_places_table] Пользователь {user_id}: финально {len(final_places)} мест")

        # Создаём таблицу заново — добавлены latitude и longitude
        cursor.execute(f"""
        CREATE TABLE '{table_name}' (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            address TEXT,
            description TEXT,
            categories TEXT,
            photo TEXT,
            rating REAL,
            latitude REAL,
            longitude REAL,
            viewed INTEGER DEFAULT 0
        )
        """)

        # Записываем в БД
        for place in final_places:
            viewed = current_viewed_state.get(place['name'], 0)
            try:
                
                cursor.execute(f"""
                INSERT INTO '{table_name}'
                (name, address, description, categories, photo, rating, latitude, longitude, viewed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    place["name"],
                    place["address"],
                    place["description"],
                    place["categories"],
                    place["photo"],
                    place["rating"],
                    place["latitude"],
                    place["longitude"],
                    viewed
                ))
            except sqlite3.Error as e:
                logger.error(f"[create_user_places_table] Ошибка вставки места {place.get('name')}: {e}")
                continue

        conn.commit()
        logger.info(f"[create_user_places_table] Пользователь {user_id}: таблица {table_name} успешно обновлена")

    except Exception as e:
        logger.error(f"[create_user_places_table] Ошибка: {e}")

    finally:
        conn.close()




@dp.callback_query(F.data == "reset_location")
async def reset_location(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = get_user(user_id)
    
    if user:
        # Сбрасываем геолокацию
        save_user(
            user_id=user_id,
            categories=user['categories'],
            wishes=user['wishes'],
            filters=user['filters'],
            latitude=None,
            longitude=None
        )
    
    # ПОЛНОСТЬЮ пересоздаем таблицу мест (так как изменилась геолокация)
    create_user_places_table(user_id)

    reset_text = """
🗺️ <b>Геолокация сброшена</b>

Ваше местоположение удалено из системы.
"""
    
    try:
        await callback.message.edit_text(
            text=reset_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🗺️ Указать геолокацию", callback_data="request_location")],
                [InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")]
            ])
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=reset_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🗺️ Указать геолокацию", callback_data="request_location")],
                [InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")]
            ])
        )
    
    await callback.answer()
    
    # Обновляем время последней активности
    update_user_activity(callback.from_user.id)


def get_places_for_user(user_id: int, limit: int = 50, offset: int = 0, sort_by_distance: bool = False) -> List[dict]:
    """
    Возвращает места для пользователя из его таблицы user_{user_id}.
    Если таблицы нет — создаёт её и наполняет местами.
    sort_by_distance: если True, сортирует по расстоянию (если есть координаты пользователя).
    """
    # Получаем данные пользователя
    print('get_places_for_user')

    user = get_user(user_id)

    user_lat = user['latitude'] if user else None
    user_lon = user['longitude'] if user else None

    conn = get_users_db_connection()
    cursor = conn.cursor()
    # Проверяем существование таблицы пользователя
    cursor.execute(f'''
    SELECT name FROM sqlite_master 
    WHERE type='table' AND name='user_{user_id}'
    ''')
    table_exists = cursor.fetchone()
    if not table_exists:
        create_user_places_table(user_id)

    cursor.execute(f'''
    SELECT id, name, address, description, categories, photo, rating, latitude, longitude
    FROM user_{user_id} 
    WHERE viewed = 0
    ORDER BY id ASC
    ''')
    rows = cursor.fetchall()

    conn.close()

    places = [
        {
            'id': row[0],
            'name': row[1],
            'address': row[2],
            'description': row[3],
            'categories': row[4],
            'photo': row[5],
            'rating': row[6],
            'latitude': row[7],
            'longitude': row[8],
        }
        for row in rows
    ]

    # 🔹 Если нужна сортировка по расстоянию
    if sort_by_distance and user_lat is not None and user_lon is not None:
        places = sort_places_by_distance(places, user_lat, user_lon)

    # 🔹 Применяем limit и offset
    if limit:
        places = places[offset:offset+limit]
    else:
        places = places[offset:]

    return places


def mark_place_as_viewed(user_id: int, place_name: str):
    """
    Помечает место как просмотренное по названию
    """
    print('mark_place_as_viewed')
    conn = get_users_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(f'''
        UPDATE user_{user_id} 
        SET viewed = 1 
        WHERE name = ?
        ''', (place_name,))
        
        conn.commit()
    except Exception as e:
        logger.error(f"Error marking place as viewed: {e}")
    finally:
        conn.close()


@dp.callback_query(F.data == "reset_viewed")
async def reset_viewed(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    conn = get_users_db_connection()
    cursor = conn.cursor()
    
    try:
        # Проверяем существование таблицы
        cursor.execute(f'''
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='user_{user_id}'
        ''')
        
        table_exists = cursor.fetchone()
        if not table_exists:
            return
        
        cursor.execute(f'''
        UPDATE user_{user_id} 
        SET viewed = 0 
        WHERE viewed = 1
        ''')
        
        conn.commit()
        logger.info(f"Reset viewed places for user {user_id}")
    except Exception as e:
        logger.error(f"Error resetting viewed places: {e}")
    finally:
        conn.close()
    
    await callback.answer()


async def reset_viewed_by_timer():
    """
    Сбрасывает значение столбца viewed до 0 во всех таблицах user_{user_id}.
    """
    try:
        # Подключаемся к главной БД, где хранятся пользователи
        conn = get_users_db_connection()
        cursor = conn.cursor()

        # Получаем всех пользователей
        cursor.execute("SELECT id FROM users")
        users = cursor.fetchall()

        # Для каждого пользователя обновляем viewed
        for (user_id,) in users:
            try:
                cursor.execute(f"UPDATE user_{user_id} SET viewed = 0")
            except Exception as e:
                print(f"Ошибка при обновлении user_{user_id}: {e}")

        conn.commit()
        conn.close()
        print("✅ Все значения viewed успешно сброшены!")
    except Exception as e:
        print(f"Ошибка при сбросе viewed: {e}")

# Клавиатуры
def get_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📍 Просмотр мест", callback_data="view_places_main"),
            InlineKeyboardButton(text="📂 Категории", callback_data="show_categories_main")
        ],
        [
            InlineKeyboardButton(text="⚙️ Фильтры", callback_data="show_filters_main"),
            InlineKeyboardButton(text="🗺️ Геолокация", callback_data="show_geolocation_main")
        ],
        [
            InlineKeyboardButton(text="❓ Помощь", callback_data="show_help_main")
        ]
    ])

def get_filters_keyboard(user_id: int, page: int = 0) -> InlineKeyboardMarkup:
    user_filters = get_user_filters(user_id)
    buttons = []
    
    # Определяем, какие фильтры показывать на текущей странице
    items_per_page = 8
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    current_filters = AVAILABLE_FILTERS[start_idx:end_idx]

    # Создаем кнопки для фильтров (по 2 в ряд)
    for i in range(0, len(current_filters), 2):
        row = []
        for filter_name in current_filters[i:i+2]:
            # Обрезаем длинные названия для лучшего отображения
            display_name = filter_name[:20] + "..." if len(filter_name) > 23 else filter_name
            emoji = "✅ " if filter_name in user_filters else ""
            # Используем индекс фильтра вместо полного названия
            filter_index = AVAILABLE_FILTERS.index(filter_name)
            row.append(InlineKeyboardButton(
                text=f"{emoji}{display_name}", 
                callback_data=f"filter_{filter_index}_{page}"  # Используем индекс и страницу
            ))
        buttons.append(row)
    
    # Кнопки навигации
    nav_buttons = []
    total_pages = (len(AVAILABLE_FILTERS) + items_per_page - 1) // items_per_page
    
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"filters_page_{page-1}"))
    
    # Добавляем индикатор страницы
    nav_buttons.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="current_page"))
    
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"filters_page_{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    # Кнопки действий
    buttons.append([InlineKeyboardButton(text="🔍 Поиск фильтра", callback_data="search_filter")])
    buttons.append([InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_filters")])
    buttons.append([InlineKeyboardButton(text="🗑️ Сбросить все фильтры", callback_data="reset_all_filters")])
    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data="main_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_categories_keyboard(user_id: int) -> InlineKeyboardMarkup:
    selected_categories = user_data.get(user_id, {}).get('selected_categories', set())
    buttons = []
    
    categories = [
        ("Семейный", "Семейный"),
        ("С друзьями", "С друзьями"),
        ("Романтический", "Романтический"),
        ("Активный", "Активный"),
        ("Спокойный", "Спокойный"),
        ("Уединённый", "Уединённый"),
        ("Культурный", "Культурный"),
        ("На воздухе", "На воздухе")
    ]
    
    for i in range(0, len(categories), 2):
        row = []
        for text, callback_data in categories[i:i+2]:
            emoji = "✅ " if callback_data in selected_categories else ""
            row.append(InlineKeyboardButton(text=f"{emoji}{text}", callback_data=callback_data))
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text="Подтвердить", callback_data="confirm_categories")])
    buttons.append([InlineKeyboardButton(text="🗑️ Сбросить все категории", callback_data="reset_all_categories")])
    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_wishes_keyboard(user_id: int) -> InlineKeyboardMarkup:
    selected_wishes = user_data.get(user_id, {}).get('selected_wishes', set())
    buttons = []
    
    wishes = [
        ("Тусовки", "Тусовки"),
        ("Вкусная еда", "Вкусная еда"),
        ("Красивый вид", "Красивый вид"),
        ("Активность", "Активность"),
        ("Развлечения", "Развлечения"),
        ("Расслабление", "Расслабление"),
        ("Музыка", "Музыка"),
        ("Атмосферность", "Атмосферность"),
        ("Творчество", "Творчество")
    ]
    
    for i in range(0, len(wishes), 2):
        row = []
        for text, callback_data in wishes[i:i+2]:
            emoji = "✅ " if callback_data in selected_wishes else ""
            row.append(InlineKeyboardButton(text=f"{emoji}{text}", callback_data=callback_data))
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text="Подтвердить", callback_data="confirm_wishes")])
    buttons.append([InlineKeyboardButton(text="🗑️ Сбросить все пожелания", callback_data="reset_all_wishes")])
    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_places_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="place_prev"),
            InlineKeyboardButton(text="Вперёд ➡️", callback_data="place_next")
        ],
        [
            InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu"),
            InlineKeyboardButton(text="❌ Место не подходит", callback_data="place_bad")
        ]
    ])

def get_back_to_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")]
    ])


@dp.callback_query(F.data == "reset_all_filters")
async def reset_all_filters(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # Сбрасываем все фильтры
    save_user_filters(user_id, [])
    
    # Обновляем сообщение
    filters_text = """
⚙️ <b>Фильтры поиска</b>

Выберите фильтры, которые хотите применить. 
Можно выбрать несколько вариантов.

<b>Текущие фильтры:</b>
❌ Фильтры не выбраны

После выбора нажмите 'Подтвердить'
"""
    
    try:
        await callback.message.edit_text(
            text=filters_text,
            reply_markup=get_filters_keyboard(user_id, 0)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=filters_text,
            reply_markup=get_filters_keyboard(user_id, 0)
        )
    
    await callback.answer("Все фильтры сброшены")
    
    # Обновляем время последней активности
    update_user_activity(callback.from_user.id, "reset_all_filters")

@dp.callback_query(F.data == "reset_all_categories")
async def reset_all_categories(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # Сбрасываем все категории
    if user_id in user_data:
        user_data[user_id]['selected_categories'] = set()
    
    # Обновляем сообщение
    categories_text = """
🎯 <b>Выбор категорий отдыха</b>

Выберите типы отдыха, которые вам интересны. 
Можно выбрать несколько вариантов.

<b>Доступные категории:</b>
• 👨‍👩‍👧‍👦 Семейный - отдых с детьми и семьей
• 👥 С друзьями - веселое времяпрепровождение в компании  
• 💕 Романтический - для пар и свиданий
• 🏃‍♂️ Активный - спорт и движение
• 🧘‍♂️ Спокойный - расслабление и отдых
• 🌿 Уединённый - тихие места для уединения
• 🎭 Культурный - музеи, театры, выставки
• 🌳 На воздухе - парки, природа, улица

После выбора нажмите "Подтвердить"
"""
    
    try:
        await callback.message.edit_text(
            text=categories_text,
            reply_markup=get_categories_keyboard(user_id)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=categories_text,
            reply_markup=get_categories_keyboard(user_id)
        )
    
    await callback.answer("Все категории сброшены")
    
    # Обновляем время последней активности
    update_user_activity(callback.from_user.id, "reset_all_categories")

@dp.callback_query(F.data == "reset_all_wishes")
async def reset_all_wishes(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # Сбрасываем все пожелания
    if user_id in user_data:
        user_data[user_id]['selected_wishes'] = set()
    
    # Обновляем сообщение
    wishes_text = """
🌟 <b>Выбор пожеланий</b>

Выберите, что для вам важно в месте отдыха. 
Можно выбрать несколько вариантов.

<b>Доступные пожелания:</b>
• 🎉 Тусовки - вечеринки и активное общение
• 🍔 Вкусная еда - гастрономические удовольствия
• 🌅 Красивый вид - живописные места и панорамы
• ⚽ Активность - игры и физическая активность
• 🎮 Развлечения - аттракционы и игры
• 😌 Расслабление - релакс и спокойствие
• 🎵 Музыка - концерты и музыкальные мероприятия
• ✨ Атмосферность - особенная атмосфера места
• 🎨 Творчество - мастер-классы и искусство

После выбора нажмите "Подтвердить"
"""
    
    try:
        await callback.message.edit_text(
            text=wishes_text,
            reply_markup=get_wishes_keyboard(user_id)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=wishes_text,
            reply_markup=get_wishes_keyboard(user_id)
        )
    
    await callback.answer("Все пожелания сброшены")
    
    # Обновляем время последней активности
    update_user_activity(callback.from_user.id, "reset_all_wishes")


# Функции для работы с сообщениями

async def delete_user_message(message: types.Message):
    """Удалить сообщение пользователя"""
    try:
        await message.delete()
    except:
        pass

async def update_or_send_message(chat_id: int, text: str, reply_markup=None, photo_url: str = None):
    """Обновить существующее сообщение или отправить новое"""
    print('update_or_send')
    if chat_id in user_messages:
        try:
            if photo_url:
                # Если есть фото, отправляем новое сообщение с фото
                message = await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_url,
                    caption=text,
                    reply_markup=reply_markup
                )
                # Удаляем старое сообщение
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=user_messages[chat_id])
                except:
                    pass
            else:
                # Если нет фото, пытаемся отредактировать текстовое сообщение
                try:
                    message = await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=user_messages[chat_id],
                        text=text,
                        reply_markup=reply_markup
                    )
                except Exception as edit_error:
                    # Если не удалось отредактировать, отправляем новое сообщение
                    logger.error(f"Error editing message, sending new: {edit_error}")
                    message = await bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=reply_markup
                    )
                    # Пытаемся удалить старое сообщение
                    try:
                        await bot.delete_message(chat_id=chat_id, message_id=user_messages[chat_id])
                    except:
                        pass
            
            user_messages[chat_id] = message.message_id
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
                        reply_markup=reply_markup
                    )
                else:
                    message = await bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=reply_markup
                    )
                user_messages[chat_id] = message.message_id
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
                    reply_markup=reply_markup
                )
            else:
                message = await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=reply_markup
                )
            user_messages[chat_id] = message.message_id
            return message.message_id
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return None

# Обработчики команд
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    print('cmd_start')
    user_id = message.from_user.id
    
    # Загружаем данные пользователя из базы данных
    user_db_data = get_user(user_id)
    if user_db_data:
        # Восстанавливаем настройки из базы данных
        user_data[user_id] = {
            'selected_categories': set(user_db_data['categories']),
            'selected_wishes': set(user_db_data['wishes']),
            'current_place_index': 0
        }
    else:
        # Создаем нового пользователя в памяти (но не в базе до выбора категорий)
        save_user(user_id)
        user_data[user_id] = {
            'selected_categories': set(),
            'selected_wishes': set(),
            'current_place_index': 0
            }

    
    welcome_text = """
🎉 <b>Добро пожаловать в Myspot!</b>

Я помогу вам найти идеальные места для отдыха по вашим предпочтениям.

<b>Основные функции:</b>
• 📍 Просмотр мест - смотрите предложения
• 📂 Категории - выберите тип отдыха
• ⚙️ Фильтры - настройте поиск
• 🗺️ Геолокация - ищите места рядом
• ❓ Помощь - получите справку

Выберите действие из меню ниже 👇
    """
    
    # Сначала отправляем приветственное сообщение
    await update_or_send_message(
        chat_id=message.chat.id,
        text=welcome_text,
        reply_markup=get_main_keyboard()
    )
    
    # Потом удаляем сообщение пользователя с командой start
    await delete_user_message(message)

# Обработчики главного меню
@dp.callback_query(F.data == "view_places_main")
async def show_places_main(callback: types.CallbackQuery):
    print('show_places_main')
    user_id = callback.from_user.id
    user = get_user(user_id)
    
    # Проверяем, есть ли непросмотренные места
    places = get_places_for_user(user_id, limit=400, offset=0, sort_by_distance=False)
    if not places:
        # Все места просмотрены
        all_viewed_text = """
🎉 <b>Все подходящие места просмотрены!</b>

Вы посмотрели все места, которые соответствуют вашим предпочтениям.

Что вы хотите сделать?
• 🔄 Сбросить историю просмотров и начать заново
• ⚙️ Изменить фильтры или категории
• 🗺️ Обновить геолокацию
"""
        
        try:
            await callback.message.edit_text(
                text=all_viewed_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Сбросить историю просмотров", callback_data="reset_viewed")],
                    [InlineKeyboardButton(text="⚙️ Изменить настройки", callback_data="main_menu")],
                    [InlineKeyboardButton(text="🗺️ Обновить геолокацию", callback_data="show_geolocation_main")]
                ])
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            chat_id = callback.message.chat.id
            await update_or_send_message(
                chat_id=chat_id,
                text=all_viewed_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Сбросить историю просмотров", callback_data="reset_viewed")],
                    [InlineKeyboardButton(text="⚙️ Изменить настройки", callback_data="main_menu")],
                    [InlineKeyboardButton(text="🗺️ Обновить геолокацию", callback_data="show_geolocation_main")]
                ])
            )
        
        await callback.answer()
        return
    # Проверяем, есть ли геолокация
    if user and user['latitude'] is not None and user['longitude'] is not None:
        # Предлагаем выбор типа просмотра
        choice_text = """
📍 <b>Выберите способ просмотра мест:</b>

• 🗺️ Ближайшие - места рядом с вами, отсортированные по расстоянию
• ⭐ Рекомендации - лучшие места по вашим предпочтениям с указанием расстояния
"""
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗺️ Ближайшие места", callback_data="view_nearby_places")],
            [InlineKeyboardButton(text="⭐ Рекомендации", callback_data="view_recommended_places")],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="main_menu")]
        ])
        
        try:
            await callback.message.edit_text(
                text=choice_text,
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            chat_id = callback.message.chat.id
            await update_or_send_message(
                chat_id=chat_id,
                text=choice_text,
                reply_markup=keyboard
            )
    else:
        # Если нет геолокации, показываем обычные рекомендации
        user_data[user_id]['current_place_index'] = 0
        user_data[user_id]['current_offset'] = 0
        
        # Сохраняем места для пользователя
        user_data[user_id]['places'] = places
        
        # Показываем первое место
        await show_place(user_id, callback.message.chat.id, 0)
    
    await callback.answer()
    
    # Обновляем время последней активности
    update_user_activity(callback.from_user.id, "view_places_main")

@dp.callback_query(F.data == "view_nearby_places")
async def view_nearby_places(callback: types.CallbackQuery):
    print('view_nearby')
    user_id = callback.from_user.id
    user_data[user_id]['current_place_index'] = 0
    user_data[user_id]['current_offset'] = 0
    
    # Получаем места с сортировкой по расстоянию
    places = get_places_for_user(user_id, limit=400, offset=0, sort_by_distance=True)
    
    if not places:
        # Обработка случая, когда нет мест
        no_places_text = """
❌ <b>Ближайшие места не найдены</b>

Не найдено мест рядом с вами.
Попробуйте изменить ваши категории, пожелания или фильтры.
"""
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📂 Изменить категории", callback_data="show_categories_main")],
            [InlineKeyboardButton(text="⚙️ Изменить фильтры", callback_data="show_filters_main")],
            [InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")]
        ])
        
        try:
            await callback.message.edit_text(
                text=no_places_text,
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            chat_id = callback.message.chat.id
            await update_or_send_message(
                chat_id=chat_id,
                text=no_places_text,
                reply_markup=keyboard
            )
        
        await callback.answer()
        return
    
    # Сохраняем места для пользователя
    user_data[user_id]['places'] = places
    
    # Показываем первое место
    await show_place(user_id, callback.message.chat.id, 0)
    
    await callback.answer()

@dp.callback_query(F.data == "view_recommended_places")
async def view_recommended_places(callback: types.CallbackQuery):
    print('view_recommended')
    user_id = callback.from_user.id
    user_data[user_id]['current_place_index'] = 0
    user_data[user_id]['current_offset'] = 0
    
    # Получаем места без сортировки по расстоянию
    places = get_places_for_user(user_id, limit=400, offset=0, sort_by_distance=False)
    
    if not places:
        # Обработка случая, когда нет мест
        no_places_text = """
❌ <b>Места не найдены</b>

Не найдено мест, соответствующих вашим предпочтениям.
Попробуйте изменить ваши категории, пожелания или фильтры.
"""
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📂 Изменить категории", callback_data="show_categories_main")],
            [InlineKeyboardButton(text="⚙️ Изменить фильтры", callback_data="show_filters_main")],
            [InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")]
        ])
        
        try:
            await callback.message.edit_text(
                text=no_places_text,
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            chat_id = callback.message.chat.id
            await update_or_send_message(
                chat_id=chat_id,
                text=no_places_text,
                reply_markup=keyboard
            )
        
        await callback.answer()
        return
    
    # Сохраняем места для пользователя
    user_data[user_id]['places'] = places
    
    # Показываем первое место
    await show_place(user_id, callback.message.chat.id, 0)
    
    await callback.answer()


@dp.callback_query(F.data == "show_categories_main")
async def show_categories_main(callback: types.CallbackQuery):
    categories_text = """
🎯 <b>Выбор категорий отдыха</b>

Выберите типы отдыха, которые вам интересны. 
Можно выбрать несколько вариантов.

<b>Доступные категории:</b>
• 👨‍👩‍👧‍👦 Семейный - отдых с детьми и семьей
• 👥 С друзьями - веселое времяпрепровождение в компании  
• 💕 Романтический - для пар и свиданий
• 🏃‍♂️ Активный - спорт и движение
• 🧘‍♂️ Спокойный - расслабление и отдых
• 🌿 Уединённый - тихие места для уединения
• 🎭 Культурный - музеи, театры, выставки
• 🌳 На воздухе - парки, природа, улица

После выбора нажмите "Подтвердить"
    """
    
    try:
        await callback.message.edit_text(
            text=categories_text,
            reply_markup=get_categories_keyboard(callback.from_user.id)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=categories_text,
            reply_markup=get_categories_keyboard(callback.from_user.id)
        )
    
    await callback.answer()
    
    # Обновляем время последней активности
    update_user_activity(callback.from_user.id, "show_categories_main")

@dp.callback_query(F.data == "show_filters_main")
async def show_filters_main(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_filters = get_user_filters(user_id)
    
    filters_text = """
⚙️ <b>Фильтры поиска</b>

Выберите фильтры, которые хотите применить. 
Можно выбрать несколько вариантов.

<b>Текущие фильтры:</b>
"""
    
    if user_filters:
        for filter_name in user_filters:
            filters_text += f"• {filter_name}\n"
    else:
        filters_text += "❌ Фильтры не выбраны\n"
    
    filters_text += "\nПосле выбора нажмите 'Подтвердить'"
    
    try:
        await callback.message.edit_text(
            text=filters_text,
            reply_markup=get_filters_keyboard(user_id, 0)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=filters_text,
            reply_markup=get_filters_keyboard(user_id, 0)
        )
    
    await callback.answer()
    
    # Обновляем время последней активности
    update_user_activity(callback.from_user.id, "show_filters_main")

@dp.callback_query(F.data.startswith("filters_page_"))
async def handle_filters_page(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    page = int(callback.data.split("_")[2])
    
    user_filters = get_user_filters(user_id)
    
    filters_text = """
⚙️ <b>Фильтры поиска</b>

Выберите фильтры, которые хотите применить. 
Можно выбрать несколько вариантов.

<b>Текущие фильтры:</b>
"""
    
    if user_filters:
        for filter_name in user_filters:
            filters_text += f"• {filter_name}\n"
    else:
        filters_text += "❌ Фильтры не выбраны\n"
    
    filters_text += "\nПосле выбора нажмите 'Подтвердить'"
    
    try:
        await callback.message.edit_text(
            text=filters_text,
            reply_markup=get_filters_keyboard(user_id, page)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=filters_text,
            reply_markup=get_filters_keyboard(user_id, page)
        )
    
    await callback.answer()
    
    # Обновляем время последней активности
    update_user_activity(callback.from_user.id)

@dp.callback_query(F.data.startswith("filter_"))
async def handle_filter_selection(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # Разбираем callback_data: filter_индекс_страница
    parts = callback.data.split("_")
    filter_index = int(parts[1])
    current_page = int(parts[2])
    
    # Получаем название фильтра по индексу
    filter_name = AVAILABLE_FILTERS[filter_index]

    user_filters = get_user_filters(user_id)
    
    # Переключаем состояние фильтра
    if filter_name in user_filters:
        user_filters.remove(filter_name)
    else:
        user_filters.append(filter_name)
    
    # Сохраняем фильтры
    save_user_filters(user_id, user_filters)
    
    # Обновляем сообщение
    user_filters = get_user_filters(user_id)
    
    filters_text = """
⚙️ <b>Фильтры поиска</b>

Выберите фильтры, которые хотите применить. 
Можно выбрать несколько вариантов.

<b>Текущие фильтры:</b>
"""
    
    if user_filters:
        for filter_name in user_filters:
            filters_text += f"• {filter_name}\n"
    else:
        filters_text += "❌ Фильтры не выбраны\n"
    
    filters_text += "\nПосле выбора нажмите 'Подтвердить'"
    
    try:
        await callback.message.edit_text(
            text=filters_text,
            reply_markup=get_filters_keyboard(user_id, current_page)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=filters_text,
            reply_markup=get_filters_keyboard(user_id, current_page)
        )
    
    await callback.answer()
    
    # Обновляем время последней активности
    update_user_activity(callback.from_user.id)

@dp.callback_query(F.data == "search_filter")
async def search_filter(callback: types.CallbackQuery, state: FSMContext):
    search_text = """
🔍 <b>Поиск фильтра</b>

Введите название фильтра, который хотите найти:
"""
    
    try:
        await callback.message.edit_text(
            text=search_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="↩️ Назад к фильтрам", callback_data="show_filters_main")]
            ])
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=search_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="↩️ Назад к фильтрам", callback_data="show_filters_main")]
            ])
        )
    
    # Устанавливаем состояние ожидания названия фильтра
    await state.set_state(FilterStates.waiting_for_filter_name)
    await callback.answer()
    
    # Обновляем время последней активности
    update_user_activity(callback.from_user.id)

@dp.message(FilterStates.waiting_for_filter_name)
async def process_filter_search(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    filter_name = message.text.strip()
    
    # Проверяем, существует ли такой фильтр
    if filter_name in AVAILABLE_FILTERS:
        # Добавляем фильтр
        user_filters = get_user_filters(user_id)
        user_filters.append(filter_name)
        save_user_filters(user_id, user_filters)
        
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
            reply_markup=get_filters_keyboard(user_id, filter_page)  # Переходим на страницу фильтра
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
            reply_markup=get_filters_keyboard(user_id, 0)
        )
    
    # Сбрасываем состояние
    await state.clear()
    
    # Удаляем сообщение пользователя
    await delete_user_message(message)
    
    # Обновляем время последней активности
    update_user_activity(message.from_user.id)


@dp.callback_query(F.data == "confirm_filters")
async def confirm_filters(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_filters = get_user_filters(user_id)
    
    # Показываем сообщение о процессе подбора
    processing_text = """
⏳ <b>Идёт подбор мест по вашим параметрам...</b>

Пожалуйста, подождите немного. Мы выбираем лучшие места, соответствующие вашим фильтрам.
"""
    
    processing_message_id = await update_or_send_message(callback.message.chat.id, processing_text)
    
    create_user_places_table(user_id)
    
    confirmation_text = f"""
✅ <b>Фильтры сохранены!</b>

<b>Выбрано фильтров:</b> {len(user_filters)}

Теперь вы можете просматривать места, соответствующие вашим предпочтениям.
"""
    
    try:
        # Удаляем сообщение о процессе
        if processing_message_id:
            try:
                await bot.delete_message(chat_id=callback.message.chat.id, message_id=processing_message_id)
            except:
                pass
        
        await callback.message.edit_text(
            text=confirmation_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📍 Смотреть места", callback_data="view_places_main")],
                [InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")]
            ])
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        
        # Удаляем сообщение о процессе
        if processing_message_id:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=processing_message_id)
            except:
                pass
        
        await update_or_send_message(
            chat_id=chat_id,
            text=confirmation_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📍 Смотреть места", callback_data="view_places_main")],
                [InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")]
            ])
        )
    
    await callback.answer()
    
    # Обновляем время последней активности
    update_user_activity(callback.from_user.id, "confirm_filters")

@dp.callback_query(F.data == "show_geolocation_main")
async def show_geolocation_main(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = get_user(user_id)
    
    geo_text = """
🗺️ <b>Поиск по геолокации</b>

Отправьте ваше местоположение, чтобы найти места рядом с вами.
"""
    
    if user and user['latitude'] is not None and user['longitude'] is not None:
        geo_text += f"""
<b>Текущее местоположение сохранено</b>
📍 Широта: {user['latitude']:.6f}
📍 Долгота: {user['longitude']:.6f}

Теперь вы можете смотреть места рядом с вами.
"""
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📍 Смотреть места рядом", callback_data="view_places_main")],
            [InlineKeyboardButton(text="🗺️ Обновить геолокацию", callback_data="request_location")],
            [InlineKeyboardButton(text="❌ Сбросить геолокацию", callback_data="reset_location")],
            [InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")]
        ])
    else:
        geo_text += """
❌ <b>Местоположение не указано</b>

Пожалуйста, отправьте ваше местоположение.
"""
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗺️ Отправить геолокацию", callback_data="request_location")],
            [InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")]
        ])
    
    try:
        await callback.message.edit_text(
            text=geo_text,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=geo_text,
            reply_markup=keyboard
        )
    
    await callback.answer()
    
    # Обновляем время последней активности
    update_user_activity(callback.from_user.id, "show_geolocation_main")


@dp.callback_query(F.data == "request_location")
async def request_location(callback: types.CallbackQuery):
    location_text = """
🗺️ <b>Отправьте ваше местоположение</b>

Пожалуйста, отправьте ваше местоположение, чтобы найти места рядом с вами.

Нажмите на кнопку "📎" (скрепка) внизу и выберите "Местоположение".
"""
    
    try:
        await callback.message.edit_text(
            text=location_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="↩️ Назад", callback_data="show_geolocation_main")]
            ])
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=location_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="↩️ Назад", callback_data="show_geolocation_main")]
            ])
        )
    
    await callback.answer()


@dp.message(F.content_type == 'location')
async def handle_location(message: types.Message):
    user_id = message.from_user.id
    latitude = message.location.latitude
    longitude = message.location.longitude
    
    # Сохраняем геолокацию пользователя
    user = get_user(user_id)
    if user:
        save_user(
            user_id=user_id,
            categories=user['categories'],
            wishes=user['wishes'],
            filters=user['filters'],
            latitude=latitude,
            longitude=longitude
        )
    else:
        # Если пользователя нет в базе, создаем запись
        save_user(
            user_id=user_id,
            categories=[],
            wishes=[],
            filters=[],
            latitude=latitude,
            longitude=longitude
        )
    
    # пересоздаем таблицу мест с новой геолокацией
    create_user_places_table(user_id)
    
    # Отправляем подтверждение
    location_text = f"""
📍 <b>Геолокация сохранена!</b>

Ваше местоположение сохранено.
Теперь вы можете искать места рядом с вами.
"""
    
    await update_or_send_message(
        chat_id=message.chat.id,
        text=location_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📍 Смотреть места рядом", callback_data="view_places_main")],
            [InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")]
        ])
    )
    
    # Удаляем сообщение с геолокацией
    await delete_user_message(message)
    
    # Обновляем время последней активности
    update_user_activity(message.from_user.id)


@dp.callback_query(F.data == "show_help_main")
async def show_help_main(callback: types.CallbackQuery):
    help_text = """
❓ <b>Помощь по использованию бота</b>

<b>Как пользоваться:</b>
1. Выберите категории отдыха
2. Укажите ваши пожелания
3. Просматривайте подобранные места
4. Используйте фильтры для уточнения

<b>Команды:</b>
/start - перезапустить бота
/help - показать эту справку
    """
    
    try:
        await callback.message.edit_text(
            text=help_text,
            reply_markup=get_back_to_main_keyboard()
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=help_text,
            reply_markup=get_back_to_main_keyboard()
        )
    
    await callback.answer()
    
    # Обновляем время последней активности
    update_user_activity(callback.from_user.id, "show_help_main")


async def show_place(user_id: int, chat_id: int, index: int):
    print('show_place')
    places = user_data[user_id].get('places', [])
    print(len(places))
    
    if not places or index >= len(places):
        return
    
    place = places[index]
    
    # Формируем текст с рейтингом
    rating = place.get('rating')
    rating_text = f"⭐ {rating}/5" if rating else "⭐ Рейтинг не указан"
    
    # Получаем категории и пожелания места из базы данных
    conn = get_places_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT categories_1, categories_2 FROM places WHERE name = ? AND address = ?', (place.get('name'), place.get('address')))
    place_details = cursor.fetchone()
    conn.close()
    
    # Формируем текст с категориями и пожеланиями
    categories_text = "Не указаны"
    wishes_text = "Не указаны"
    
    if place_details:
        if place_details['categories_1']:
            categories_text = place_details['categories_1']
        if place_details['categories_2']:
            wishes_text = place_details['categories_2']
    # Получаем геолокацию пользователя
    user = get_user(user_id)
    distance_text = ""
    
    if user and user['latitude'] and user['longitude'] and place.get('latitude') and place.get('longitude'):
        try:
            from math import radians, sin, cos, sqrt, atan2
            
            user_lat = user['latitude']
            user_lon = user['longitude']
            place_lat = float(place['latitude'])
            place_lon = float(place['longitude'])
            
            # Расчет расстояния
            R = 6371  # Радиус Земли в км
            lat1_rad = radians(user_lat)
            lon1_rad = radians(user_lon)
            lat2_rad = radians(place_lat)
            lon2_rad = radians(place_lon)
            
            dlon = lon2_rad - lon1_rad
            dlat = lat2_rad - lat1_rad
            
            a = sin(dlat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon/2)**2
            c = 2 * atan2(sqrt(a), sqrt(1-a))
            
            distance = R * c
            distance_text = f"\n<b>Расстояние:</b> {distance:.1f} км от вас"
            
        except (ValueError, TypeError):
            # Если координаты некорректны, пропускаем
            pass
    print(len(places))
    place_text = f"""
<b>Название места:</b> {place.get('name', 'Не указано')}
<b>Фильтры:</b> {place.get('categories', 'Не указаны')}
<b>Категории:</b> {categories_text}
<b>Пожелания:</b> {wishes_text}
<b>Рейтинг:</b> {rating_text}{distance_text}
<b>Описание:</b> {place.get('description', 'Описание отсутствует')}
<b>Адрес:</b> {place.get('address', 'Адрес не указан')}
    """
    
    # Получаем ссылку на фото и проверяем ее валидность
    photo_url = place.get('photo')
    
    # Проверяем, является ли photo_url валидной ссылкой
    if photo_url and isinstance(photo_url, str) and photo_url.startswith(('http://', 'https://')):
        try:
            await update_or_send_message(
                chat_id=chat_id,
                text=place_text,
                reply_markup=get_places_keyboard(),
                photo_url=photo_url
            )
        except Exception as e:
            logger.error(f"Error sending photo message: {e}")
            # Если не удалось отправить с фото, отправляем без фото
            await update_or_send_message(
                chat_id=chat_id,
                text=place_text,
                reply_markup=get_places_keyboard()
            )
    else:
        # Если фото нет или ссылка невалидна, отправляем без фото
        await update_or_send_message(
            chat_id=chat_id,
            text=place_text,
            reply_markup=get_places_keyboard()
        )
    # Помечаем место как просмотренное по названию
    mark_place_as_viewed(user_id, place.get('name'))

# Обработчики инлайн кнопок
@dp.callback_query(F.data.in_(["Семейный", "С друзьями", "Романтический", "Активный", "Спокойный", "Уединённый", "Культурный", "На воздухе"]))
async def handle_category_selection(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    category = callback.data
    
    if user_id not in user_data:
        user_data[user_id] = {'selected_categories': set(), 'selected_wishes': set()}
    
    if category in user_data[user_id]['selected_categories']:
        user_data[user_id]['selected_categories'].remove(category)
    else:
        user_data[user_id]['selected_categories'].add(category)
    
    # Обновляем сообщение с новым состоянием кнопок
    categories_text = """
🎯 <b>Выбор категорий отдыха</b>

Выберите типы отдыха, которые вам интересны. 
Можно выбрать несколько вариантов.

<b>Доступные категории:</b>
• 👨‍👩‍👧‍👦 Семейный - отдых с детьми и семьей
• 👥 С друзьями - веселое времяпрепровождение в компании  
• 💕 Романтический - для пар и свиданий
• 🏃‍♂️ Активный - спорт и движение
• 🧘‍♂️ Спокойный - расслабление и отдых
• 🌿 Уединённый - тихие места для уединения
• 🎭 Культурный - музеи, театры, выставки
• 🌳 На воздухе - парки, природа, улица

После выбора нажмите "Подтвердить"
    """
    
    try:
        await callback.message.edit_text(
            text=categories_text,
            reply_markup=get_categories_keyboard(user_id)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        # Если не удалось отредактировать, отправляем новое сообщение
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=categories_text,
            reply_markup=get_categories_keyboard(user_id)
        )
    
    await callback.answer()
    
    # Обновляем время последней активности
    update_user_activity(callback.from_user.id)

@dp.callback_query(F.data == "confirm_categories")
async def confirm_categories(callback: types.CallbackQuery):
    wishes_text = """
🌟 <b>Выбор пожеланий</b>

Выберите, что для вам важно в месте отдыха. 
Можно выбрать несколько вариантов.

<b>Доступные пожелания:</b>
• 🎉 Тусовки - вечеринки и активное общение
• 🍔 Вкусная еда - гастрономические удовольствия
• 🌅 Красивый вид - живописные места и панорамы
• ⚽ Активность - игры и физическая активность
• 🎮 Развлечения - аттракционы и игры
• 😌 Расслабление - релакс и спокойствие
• 🎵 Музыка - концерты и музыкальные мероприятия
• ✨ Атмосферность - особенная атмосфера места
• 🎨 Творчество - мастер-классы и искусство

После выбора нажмите "Подтвердить"
    """
    
    try:
        await callback.message.edit_text(
            text=wishes_text,
            reply_markup=get_wishes_keyboard(callback.from_user.id)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=wishes_text,
            reply_markup=get_wishes_keyboard(callback.from_user.id)
        )
    
    await callback.answer()
    
    # Обновляем время последней активности
    update_user_activity(callback.from_user.id, "confirm_categories")

@dp.callback_query(F.data.in_(["Тусовки", "Вкусная еда", "Красивый вид", "Активность", "Развлечения", "Расслабление", "Музыка", "Атмосферность", "Творчество"]))
async def handle_wish_selection(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    wish = callback.data
    
    if user_id not in user_data:
        user_data[user_id] = {'selected_categories': set(), 'selected_wishes': set()}
    
    if wish in user_data[user_id]['selected_wishes']:
        user_data[user_id]['selected_wishes'].remove(wish)
    else:
        user_data[user_id]['selected_wishes'].add(wish)
    
    # Обновляем сообщение
    wishes_text = """
🌟 <b>Выбор пожеланий</b>

Выберите, что для вам важно в месте отдыха. 
Можно выбрать несколько вариантов.

<b>Доступные пожелания:</b>
• 🎉 Тусовки - вечеринки и активное общение
• 🍔 Вкусная еда - гастрономические удовольствия
• 🌅 Красивый вид - живописные места и панорамы
• ⚽ Активность - игры и физическая активность
• 🎮 Развлечения - аттракционы и игры
• 😌 Расслабление - релакс и спокойствие
• 🎵 Музыка - концерты и музыкальные мероприятия
• ✨ Атмосферность - особенная атмосфера места
• 🎨 Творчество - мастер-классы и искусство

После выбора нажмите "Подтвердить"
    """
    
    try:
        await callback.message.edit_text(
            text=wishes_text,
            reply_markup=get_wishes_keyboard(user_id)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=wishes_text,
            reply_markup=get_wishes_keyboard(user_id)
        )
    
    await callback.answer()
    
    # Обновляем время последней активности
    update_user_activity(callback.from_user.id)


@dp.callback_query(F.data == "confirm_wishes")
async def confirm_wishes(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    categories_count = len(user_data[user_id]['selected_categories'])
    wishes_count = len(user_data[user_id]['selected_wishes'])
    
    # Показываем сообщение о процессе подбора
    processing_text = """
⏳ <b>Идёт подбор мест по вашим параметрам...</b>

Пожалуйста, подождите немного. Мы анализируем ваши категории и пожелания для подбора идеальных мест.
"""
    
    processing_message_id = await update_or_send_message(callback.message.chat.id, processing_text)
    
    # Получаем текущие данные пользователя из базы (включая геопозицию)
    user = get_user(user_id)
    
    # Сохраняем пользователя в базу данных с сохранением геопозиции
    save_user(
        user_id=user_id,
        categories=list(user_data[user_id]['selected_categories']),
        wishes=list(user_data[user_id]['selected_wishes']),
        filters=user['filters'] if user else [],  # Сохраняем текущие фильтры
        latitude=user['latitude'] if user else None,  # Сохраняем геопозицию
        longitude=user['longitude'] if user else None   # Сохраняем геопозицию
    )

    create_user_places_table(user_id)
    
    confirmation_text = f"""
<b>Настройки сохранены!</b>

<b>Выбрано категорий:</b> {categories_count}
<b>Выбрано пожеланий:</b> {wishes_count}
<b>Выбрано фильтры:</b> {len(user['filters']) if user else 0}

История просмотров сброшена. Теперь вы можете просматривать места, соответствующие вашим новым предпочтениям.
    """
    
    try:
        # Удаляем сообщение о процессе
        if processing_message_id:
            try:
                await bot.delete_message(chat_id=callback.message.chat.id, message_id=processing_message_id)
            except:
                pass
        
        await callback.message.edit_text(
            text=confirmation_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📍 Смотреть места", callback_data="view_places_main")],
                [InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")]
            ])
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        
        # Удаляем сообщение о процессе
        if processing_message_id:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=processing_message_id)
            except:
                pass
        
        await update_or_send_message(
            chat_id=chat_id,
            text=confirmation_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📍 Смотреть места", callback_data="view_places_main")],
                [InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")]
            ])
        )
    
    await callback.answer()
    
    # Обновляем время последней активности
    update_user_activity(callback.from_user.id, "confirm_wishes")


@dp.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: types.CallbackQuery):
    main_text = """
🎉 <b>Добро пожаловать в MySpot!</b>

Я помогу вам найти идеальные места для отдыха по вашим предпочтениям.

<b>Основные функции:</b>
• 📍 Просмотр мест - смотрите предложения
• 📂 Категории - выберите тип отдыха
• ⚙️ Фильтры - настройте поиск
• 🗺️ Геолокация - ищите места рядом
• ❓ Помощь - получите справку

Выберите действие из меню ниже 👇
    """
    
    try:
        # Пытаемся отредактировать сообщение
        await callback.message.edit_text(
            text=main_text,
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        # Если не удалось отредактировать (например, сообщение с фото), отправляем новое
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        
        # Сначала отправляем новое сообщение
        await update_or_send_message(
            chat_id=chat_id,
            text=main_text,
            reply_markup=get_main_keyboard()
        )
        
        # Затем пытаемся удалить старое сообщение
        try:
            await bot.delete_message(chat_id=chat_id, message_id=callback.message.message_id)
        except Exception as delete_error:
            logger.error(f"Error deleting old message: {delete_error}")
    
    await callback.answer()
    
    # Обновляем время последней активности
    update_user_activity(callback.from_user.id, "main_menu")


@dp.callback_query(F.data.in_(["place_prev", "place_next"]))
async def navigate_places(callback: types.CallbackQuery):
    print('navigate')
    user_id = callback.from_user.id
    current_index = user_data[user_id].get('current_place_index', 0)
    places = user_data[user_id].get('places', [])
    
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
            all_viewed_text = """
🎉 <b>Все подходящие места просмотрены!</b>

Вы посмотрели все места, которые соответствуют вашим предпочтениям.

Что вы хотите сделать?
• 🔄 Сбросить историю просмотров и начать заново
• ⚙️ Изменить фильтры или категории
• 🗺️ Обновить геолокацию
"""
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Сбросить историю просмотров", callback_data="reset_viewed")],
                [InlineKeyboardButton(text="⚙️ Изменить настройки", callback_data="main_menu")],
                [InlineKeyboardButton(text="🗺️ Обновить геолокацию", callback_data="show_geolocation_main")]
            ])
            try:
                await callback.message.edit_text(
                    text=all_viewed_text,
                    reply_markup=keyboard
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
                chat_id = callback.message.chat.id
                await update_or_send_message(
                    chat_id=chat_id,
                    text=all_viewed_text,
                    reply_markup=keyboard
                )
            await callback.answer()
            return
    
    user_data[user_id]['current_place_index'] = current_index
    
    # Показываем место
    await show_place(user_id, callback.message.chat.id, current_index)
    
    await callback.answer()
    
    # Обновляем время последней активности
    update_user_activity(callback.from_user.id)


# Обработчик отмены состояния фильтра
@dp.callback_query(F.data == "show_filters_main", FilterStates.waiting_for_filter_name)
async def cancel_filter_search(callback: types.CallbackQuery, state: FSMContext):
    print('-----------')
    user_id = callback.from_user.id
    user_filters = get_user_filters(user_id)
    
    filters_text = """
⚙️ <b>Фильтры поиска</b>

Выберите фильтры, которые хотите применить. 
Можно выбрать несколько вариантов.

<b>Текущие фильтры:</b>
"""
    
    if user_filters:
        for filter_name in user_filters:
            filters_text += f"• {filter_name}\n"
    else:
        filters_text += "❌ Фильтры не выбраны\n"
    
    filters_text += "\nПосле выбора нажмите 'Подтвердить'"

    try:
        await callback.message.edit_text(
            text=filters_text,
            reply_markup=get_filters_keyboard(user_id, 0)
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        chat_id = callback.message.chat.id
        await update_or_send_message(
            chat_id=chat_id,
            text=filters_text,
            reply_markup=get_filters_keyboard(user_id, 0)
        )
    
    # Сбрасываем состояние
    await state.clear()
    
    await callback.answer()
    
    # Обновляем время последней активности
    update_user_activity(callback.from_user.id)

# Обработчик всех текстовых сообщений (удаление)
@dp.message()
async def delete_all_messages(message: types.Message):
    await delete_user_message(message)
    
    # Обновляем время последней активности
    update_user_activity(message.from_user.id)

# Запуск бота
async def main():
    scheduler = AsyncIOScheduler(timezone=pytz.timezone("Europe/Moscow"))
    scheduler.add_job(reset_viewed_by_timer, CronTrigger(hour=4, minute=0))
    scheduler.start()
    logger.info("Starting single-message bot with database support...")
    print("Планировщик задач:", scheduler.get_jobs())

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())