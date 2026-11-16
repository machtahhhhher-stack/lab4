"""Клавиатуры бота: обычная (под полем ввода) и встроенные кнопки под сообщениями."""
from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
                           ReplyKeyboardMarkup)

from movies.models import Film, FilmShort, TopItem
from movies.storage import LANGUAGES, UserSettings

# Тексты кнопок главного меню - по ним же бот узнаёт нажатие
BTN_SEARCH = "🔎 Поиск"
BTN_TOP = "🏆 Топ"
BTN_RANDOM = "🎲 Случайный"
BTN_FAVORITES = "⭐ Избранное"
BTN_SETTINGS = "⚙️ Настройки"
BTN_HELP = "❓ Помощь"

MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_SEARCH), KeyboardButton(text=BTN_TOP), KeyboardButton(text=BTN_RANDOM)],
              [KeyboardButton(text=BTN_FAVORITES), KeyboardButton(text=BTN_SETTINGS), KeyboardButton(text=BTN_HELP)]],
    resize_keyboard=True,
    input_field_placeholder="Название фильма…",
)


def short(text: str, size: int = 60) -> str:
    """У кнопки ограничена длина текста - длинные подписи обрезаем."""
    return text if len(text) <= size else text[:size - 1] + "…"


# callback_data - это «подпись» нажатой кнопки, по ней бот понимает, что делать.
# Формат: "действие:значение", например "film:Q83495".

def search_results(films: list[FilmShort]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=short(str(f)), callback_data=f"film:{f.id}")] for f in films])


def film_buttons(film: Film, is_favorite: bool) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="💔 Убрать из избранного" if is_favorite else "⭐ В избранное",
                                  callback_data=f"fav:{film.id}")]]
    links = []
    if film.wiki_url:
        links.append(InlineKeyboardButton(text="📖 Википедия", url=film.wiki_url))
    if film.imdb_url:
        links.append(InlineKeyboardButton(text="🎞 IMDb", url=film.imdb_url))
    links.append(InlineKeyboardButton(text="🗂 Wikidata", url=film.wikidata_url))
    rows.append(links)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def top_buttons(items: list[TopItem]) -> InlineKeyboardMarkup:
    # из топа ищем фильм по названию: в callback_data влезает только 64 байта
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=short(f"{i.place}. {i.title}"),
                              callback_data=f"find:{i.title.encode('utf-8')[:58].decode('utf-8', 'ignore')}")]
        for i in items])


def favorites_buttons(user: UserSettings) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=short(title), callback_data=f"film:{film_id}")]
        for film_id, title in user.favorites.items()])


def history_buttons(user: UserSettings) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=short(query), callback_data=f"find:{query.encode('utf-8')[:58].decode('utf-8', 'ignore')}")]
        for query in user.history])


def settings_buttons(user: UserSettings) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🌐 Язык: {LANGUAGES.get(user.lang, user.lang)}", callback_data="set:lang")],
        [InlineKeyboardButton(text=f"🔢 Результатов: {user.results}", callback_data="set:results")],
        [InlineKeyboardButton(text=f"🖼 Постеры: {'да' if user.posters else 'нет'}", callback_data="set:posters")],
        [InlineKeyboardButton(text="🗑 Очистить историю", callback_data="set:clear_history")],
    ])
