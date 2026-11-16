"""Тексты сообщений бота. Разметка - HTML (Telegram понимает <b>, <i>, <a>)."""
from html import escape

from movies.models import Film, TopItem
from movies.storage import LANGUAGES, UserSettings

CAPTION_LIMIT = 1024   # Telegram: подпись к фото не длиннее 1024 символов
TEXT_LIMIT = 4096

START = (
    "🎬 <b>Привет! Я бот-справочник по фильмам.</b>\n\n"
    "Напишите название фильма — например, <i>Интерстеллар</i> или <i>Матрица</i>, "
    "и я покажу год, режиссёра, жанры, бюджет, сборы и оценки IMDb, Metacritic и Rotten Tomatoes.\n\n"
    "Кнопки внизу: поиск, топ фильмов, случайный фильм, избранное и настройки. "
    "Список всех команд — /help."
)

HELP = (
    "<b>Как пользоваться</b>\n\n"
    "• просто напишите название фильма;\n"
    "• /search <i>название</i> — то же самое командой;\n"
    "• /top — топ-10 продаж фильмов iTunes (рейтинг);\n"
    "• /random — случайный фильм из топа;\n"
    "• /favorites — избранное (⭐ в карточке фильма);\n"
    "• /history — последние запросы;\n"
    "• /settings — язык, число результатов, постеры;\n"
    "• /help — эта справка.\n\n"
    "Данные: Викиданные и Википедия, топ — iTunes. Настройки сохраняются."
)


def money(amount: float | None) -> str:
    if amount is None:
        return "—"
    if amount >= 1e9:
        return f"${amount / 1e9:.2f} млрд".replace(".", ",")
    if amount >= 1e6:
        return f"${amount / 1e6:.1f} млн".replace(".", ",").replace(",0 ", " ")
    return f"${amount:,.0f}".replace(",", " ")


def duration(minutes: int | None) -> str:
    if not minutes:
        return "—"
    hours, mins = divmod(minutes, 60)
    return f"{hours} ч {mins:02d} мин" if hours else f"{mins} мин"


def film_card(film: Film, limit: int = TEXT_LIMIT) -> str:
    """Карточка фильма. Все данные из интернета экранируем: в названии может
    оказаться «<» или «&», и Telegram не поймёт разметку."""
    lines = [f"🎬 <b>{escape(film.title)}</b>" + (f" ({film.year})" if film.year else "")]
    if film.directors:
        lines.append(f"🎥 Режиссёр: {escape(', '.join(film.directors))}")
    if film.genres:
        lines.append(f"🎭 Жанр: {escape(', '.join(film.genres))}")
    if film.countries:
        lines.append(f"🌍 Страна: {escape(', '.join(film.countries))}")
    lines.append(f"⏱ Длительность: {duration(film.duration)}")
    if film.budget or film.box_office:
        lines.append(f"💰 Бюджет: {money(film.budget)}, сборы: {money(film.box_office)}")
    if film.ratings:
        lines.append("⭐ Оценки: " + ", ".join(f"{escape(k)} {escape(v)}" for k, v in film.ratings.items()))
    head = "\n".join(lines)
    if film.summary:
        # описание обрезаем так, чтобы всё сообщение влезло в ограничение Telegram
        room = limit - len(head) - 10
        summary = film.summary if len(film.summary) <= room else film.summary[:room].rsplit(" ", 1)[0] + "…"
        if room > 50:
            head += "\n\n" + escape(summary)
    return head


def top_list(items: list[TopItem]) -> str:
    lines = ["🏆 <b>Топ продаж фильмов iTunes</b>\n"]
    for item in items:
        extra = ", ".join(x for x in (item.genre, item.year) if x)
        lines.append(f"{item.place}. {escape(item.title)}" + (f" <i>({escape(extra)})</i>" if extra else ""))
    lines.append("\nНажмите на фильм, чтобы открыть карточку.")
    return "\n".join(lines)


def settings_text(user: UserSettings) -> str:
    return ("⚙️ <b>Настройки</b>\n\n"
            f"Язык данных: {LANGUAGES.get(user.lang, user.lang)}\n"
            f"Результатов в поиске: {user.results}\n"
            f"Постеры: {'показывать' if user.posters else 'не показывать'}\n\n"
            "Нажмите на кнопку, чтобы изменить. Настройки сохраняются.")


def favorites_text(user: UserSettings) -> str:
    if not user.favorites:
        return "⭐ В избранном пока пусто. Откройте фильм и нажмите «⭐ В избранное»."
    return f"⭐ <b>Избранное</b> ({len(user.favorites)}):"


def history_text(user: UserSettings) -> str:
    if not user.history:
        return "🕘 Вы ещё ничего не искали."
    return "🕘 <b>Последние запросы</b> — нажмите, чтобы повторить:"
