from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.instances import db_service

AVAILABLE_FILTERS = [
    "Кафе",
    "Ресторан",
    "Кофейня",
    "Бар",
    "Пиццерия",
    "Суши-бар",
    "Столовая",
    "Паб",
    "Чай с собой",
    "Парк культуры и отдыха",
    "Кинотеатр",
    "Театр",
    "Концертный зал",
    "Музей",
    "Художественная галерея",
    "Выставка",
    "Выставочный центр",
    "Культурный центр",
    "Библиотека",
    "Планетарий",
    "Океанариум",
    "Аквапарк",
    "Бассейн",
    "Каток",
    "Спортивный комплекс",
    "Спортивный клуб",
    "Фитнес-центр",
    "Спортивная школа",
    "Скалодром",
    "Боулинг-клуб",
    "Квесты",
    "Клуб виртуальной реальности",
    "Лазертаг",
    "Пейнтбол",
    "Картинг",
    "Батутный центр",
    "Верёвочный парк",
    "Аттракцион",
    "Парк аттракционов",
    "Детская площадка",
    "Игровая комната",
    "Клуб для детей и подростков",
    "Центр развития ребёнка",
    "Детский лагерь отдыха",
    "Организация и проведение детских праздников",
    "Ночной клуб",
    "Караоке-клуб",
    "Караоке-кабинка",
    "Кальян-бар",
    "Стриптиз-клуб",
    "Банкетный зал",
    "Кейтеринг",
    "Аренда площадок для культурно-массовых мероприятий",
    "Антикафе",
    "Водные прогулки",
    "Пляж",
    "Сауна",
    "Часовня",
    "Смотровая площадка",
    "Сквер",
    "Сад",
    "Лесопарк",
    "Заповедник",
    "Место для пикника",
    "Алкогольные напитки",
    "Рюмочная",
    "Пивоварня",
    "Пивоваренный завод",
    "Сыроварня",
    "Торговый центр",
    "Игорное и развлекательное оборудование",
    "Бильярдный клуб",
    "Игровые приставки",
    "Компьютерный клуб",
    "Киберспорт",
    "Настольные и интеллектуальные игры",
    "Театрально-концертная касса",
    "Концертные и театральные агентства",
    "Горная вершина",
    "Обсерватория",
    "Аэроклуб",
    "Аэротруба",
    "Центр экстремальных видов спорта",
    "Зимние развлечения",
    "Ретритный центр",
    "Декоративный объект",
    "Чайная",
    "Безалкогольный бар",
    "Скейт-парк",
    "Танцплощадка",
    "Оркестр",
    "Тир",
    "Лодочная станция",
    "Водная база",
]

user_data: dict[int, dict[Any, Any]] = {}


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


# Клавиатуры


async def get_filters_keyboard(user_id: int, page: int = 0) -> InlineKeyboardMarkup:
    user_filters = await db_service.get_user_filters(user_id)
    buttons = []

    # Определяем, какие фильтры показывать на текущей странице
    items_per_page = 8
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    current_filters = AVAILABLE_FILTERS[start_idx:end_idx]

    # Создаем кнопки для фильтров (по 2 в ряд)
    for i in range(0, len(current_filters), 2):
        row = []
        for filter_name in current_filters[i : i + 2]:
            # Обрезаем длинные названия для лучшего отображения
            display_name = filter_name[:20] + "..." if len(filter_name) > 23 else filter_name
            emoji = "✅ " if filter_name in user_filters else ""
            # Используем индекс фильтра вместо полного названия
            filter_index = AVAILABLE_FILTERS.index(filter_name)
            row.append(
                InlineKeyboardButton(
                    text=f"{emoji}{display_name}",
                    callback_data=f"filter_{filter_index}_{page}",  # Используем индекс и страницу
                )
            )
        buttons.append(row)

    # Кнопки навигации
    nav_buttons = []
    total_pages = (len(AVAILABLE_FILTERS) + items_per_page - 1) // items_per_page

    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"filters_page_{page - 1}"))

    # Добавляем индикатор страницы
    nav_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="current_page"))

    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"filters_page_{page + 1}"))

    if nav_buttons:
        buttons.append(nav_buttons)

    # Кнопки действий
    buttons.append([InlineKeyboardButton(text="🔍 Поиск фильтра", callback_data="search_filter")])
    buttons.append([InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_filters")])
    buttons.append([InlineKeyboardButton(text="🗑️ Сбросить все фильтры", callback_data="reset_all_filters")])
    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data="main_menu")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📍 Просмотр мест", callback_data="view_places_main"),
                InlineKeyboardButton(text="📂 Категории", callback_data="show_categories_main"),
            ],
            [
                InlineKeyboardButton(text="⚙️ Фильтры", callback_data="show_filters_main"),
                InlineKeyboardButton(text="🗺️ Геолокация", callback_data="show_geolocation_main"),
            ],
            [InlineKeyboardButton(text="❓ Помощь", callback_data="show_help_main")],
        ]
    )


def get_categories_keyboard(user_id: int) -> InlineKeyboardMarkup:
    selected_categories = user_data.get(user_id, {}).get("selected_categories", set())
    buttons = []

    categories = [
        ("Семейный", "Семейный"),
        ("С друзьями", "С друзьями"),
        ("Романтический", "Романтический"),
        ("Активный", "Активный"),
        ("Спокойный", "Спокойный"),
        ("Уединённый", "Уединённый"),
        ("Культурный", "Культурный"),
        ("На воздухе", "На воздухе"),
    ]

    for i in range(0, len(categories), 2):
        row = []
        for text, callback_data in categories[i : i + 2]:
            emoji = "✅ " if callback_data in selected_categories else ""
            row.append(InlineKeyboardButton(text=f"{emoji}{text}", callback_data=callback_data))
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="Подтвердить", callback_data="confirm_categories")])
    buttons.append([InlineKeyboardButton(text="🗑️ Сбросить все категории", callback_data="reset_all_categories")])
    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_wishes_keyboard(user_id: int) -> InlineKeyboardMarkup:
    selected_wishes = user_data.get(user_id, {}).get("selected_wishes", set())
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
        ("Творчество", "Творчество"),
    ]

    for i in range(0, len(wishes), 2):
        row = []
        for text, callback_data in wishes[i : i + 2]:
            emoji = "✅ " if callback_data in selected_wishes else ""
            row.append(InlineKeyboardButton(text=f"{emoji}{text}", callback_data=callback_data))
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="Подтвердить", callback_data="confirm_wishes")])
    buttons.append([InlineKeyboardButton(text="🗑️ Сбросить все пожелания", callback_data="reset_all_wishes")])
    buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_places_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="place_prev"),
                InlineKeyboardButton(text="Вперёд ➡️", callback_data="place_next"),
            ],
            [
                InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu"),
                InlineKeyboardButton(text="❌ С местом что-то не так", callback_data="place_bad"),
            ],
        ]
    )


def get_back_to_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="↩️ Главное меню", callback_data="main_menu")]]
    )
