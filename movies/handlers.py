"""Обработчики: что бот делает в ответ на команды, текст и нажатия кнопок.

Объекты api (MovieApi) и store (UserStore) aiogram сам передаёт в каждый
обработчик - они зарегистрированы в Dispatcher в bot.py.
"""
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, ErrorEvent, Message

from movies import keyboards as kb
from movies import texts
from movies.api import MovieApi
from movies.errors import ApiError, BotError, NotFoundError, StorageError
from movies.storage import UserStore

router = Router()
log = logging.getLogger(__name__)


# ------------------------------------------------------------------ команды
@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(texts.START, reply_markup=kb.MAIN_MENU)


@router.message(Command("help"))
@router.message(F.text == kb.BTN_HELP)
async def cmd_help(message: Message) -> None:
    await message.answer(texts.HELP, reply_markup=kb.MAIN_MENU)


@router.message(Command("search"))
async def cmd_search(message: Message, command: CommandObject, api: MovieApi, store: UserStore) -> None:
    if not command.args:
        await message.answer("Напишите название после команды, например: /search Матрица")
        return
    await do_search(message, command.args, api, store)


@router.message(F.text == kb.BTN_SEARCH)
async def btn_search(message: Message) -> None:
    await message.answer("Напишите название фильма 👇")


@router.message(Command("top"))
@router.message(F.text == kb.BTN_TOP)
async def cmd_top(message: Message, api: MovieApi) -> None:
    items = await api.top(limit=10)
    await message.answer(texts.top_list(items), reply_markup=kb.top_buttons(items))


@router.message(Command("random"))
@router.message(F.text == kb.BTN_RANDOM)
async def cmd_random(message: Message, api: MovieApi, store: UserStore) -> None:
    await message.answer("🎲 Выбираю фильм…")
    user = store.get(message.from_user.id)
    film = await api.random_film(user.lang)
    await send_film(message, film.id, api, store, film=film)


@router.message(Command("favorites"))
@router.message(F.text == kb.BTN_FAVORITES)
async def cmd_favorites(message: Message, store: UserStore) -> None:
    user = store.get(message.from_user.id)
    await message.answer(texts.favorites_text(user),
                         reply_markup=kb.favorites_buttons(user) if user.favorites else None)


@router.message(Command("history"))
async def cmd_history(message: Message, store: UserStore) -> None:
    user = store.get(message.from_user.id)
    await message.answer(texts.history_text(user),
                         reply_markup=kb.history_buttons(user) if user.history else None)


@router.message(Command("settings"))
@router.message(F.text == kb.BTN_SETTINGS)
async def cmd_settings(message: Message, store: UserStore) -> None:
    user = store.get(message.from_user.id)
    await message.answer(texts.settings_text(user), reply_markup=kb.settings_buttons(user))


# ------------------------------------------------------------------ обычный текст = поиск
@router.message(F.text & ~F.text.startswith("/"))
async def text_search(message: Message, api: MovieApi, store: UserStore) -> None:
    await do_search(message, message.text, api, store)


@router.message(F.text.startswith("/"))
async def unknown_command(message: Message) -> None:
    await message.answer("Не знаю такой команды 🤔 Список команд — /help")


@router.message()
async def not_text(message: Message) -> None:
    # прислали стикер, фото, голосовое...
    await message.answer("Я понимаю только текст: напишите название фильма ✍️")


# ------------------------------------------------------------------ кнопки под сообщениями
@router.callback_query(F.data.startswith("film:"))
async def cb_film(callback: CallbackQuery, api: MovieApi, store: UserStore) -> None:
    await callback.answer()   # убираем «часики» на кнопке
    await send_film(callback.message, callback.data.split(":", 1)[1], api, store,
                    user_id=callback.from_user.id)


@router.callback_query(F.data.startswith("find:"))
async def cb_find(callback: CallbackQuery, api: MovieApi, store: UserStore) -> None:
    await callback.answer()
    await do_search(callback.message, callback.data.split(":", 1)[1], api, store,
                    user_id=callback.from_user.id)


@router.callback_query(F.data.startswith("fav:"))
async def cb_favorite(callback: CallbackQuery, api: MovieApi, store: UserStore) -> None:
    film_id = callback.data.split(":", 1)[1]
    user = store.get(callback.from_user.id)
    film = await api.film(film_id, user.lang)
    added = user.toggle_favorite(film_id, film.title)
    store.save()
    await callback.answer("Добавлено в избранное ⭐" if added else "Убрано из избранного")
    # обновляем кнопку под карточкой
    await callback.message.edit_reply_markup(reply_markup=kb.film_buttons(film, added))


@router.callback_query(F.data.startswith("set:"))
async def cb_settings(callback: CallbackQuery, store: UserStore) -> None:
    user = store.get(callback.from_user.id)
    action = callback.data.split(":", 1)[1]
    if action == "lang":
        user.next_lang()
    elif action == "results":
        user.next_results()
    elif action == "posters":
        user.posters = not user.posters
    elif action == "clear_history":
        user.history.clear()
    store.save()
    await callback.answer("Сохранено ✅")
    try:
        await callback.message.edit_text(texts.settings_text(user), reply_markup=kb.settings_buttons(user))
    except TelegramBadRequest:
        pass   # «message is not modified» - текст не изменился, это не ошибка


# ------------------------------------------------------------------ общие действия
async def do_search(message: Message, query: str, api: MovieApi, store: UserStore,
                    user_id: int | None = None) -> None:
    user = store.get(user_id or message.from_user.id)
    films = await api.search(query, user.lang, limit=user.results)
    user.remember_query(query.strip())
    store.save()
    if len(films) == 1:   # нашёлся ровно один фильм - сразу показываем карточку
        await send_film(message, films[0].id, api, store, user_id=user_id)
        return
    await message.answer(f"🔎 Нашлось фильмов: {len(films)}. Выберите:",
                         reply_markup=kb.search_results(films))


async def send_film(message: Message, film_id: str, api: MovieApi, store: UserStore,
                    user_id: int | None = None, film=None) -> None:
    user = store.get(user_id or message.from_user.id)
    film = film or await api.film(film_id, user.lang)
    buttons = kb.film_buttons(film, film.id in user.favorites)
    if user.posters and film.poster:
        try:
            await message.answer_photo(film.poster, caption=texts.film_card(film, texts.CAPTION_LIMIT),
                                       reply_markup=buttons)
            return
        except TelegramBadRequest:
            pass   # Telegram не смог скачать картинку - пришлём просто текст
    await message.answer(texts.film_card(film), reply_markup=buttons, disable_web_page_preview=True)


# ------------------------------------------------------------------ ошибки
@router.errors()
async def on_error(event: ErrorEvent) -> bool:
    """Сюда попадает любое исключение из обработчиков. Отвечаем пользователю
    понятным текстом, а бот продолжает работать."""
    error = event.exception
    if isinstance(error, NotFoundError):
        text = f"😕 {error}"
    elif isinstance(error, ApiError):
        text = f"⚠️ Сервис с данными о фильмах сейчас недоступен: {error}"
    elif isinstance(error, StorageError):
        text = f"⚠️ {error}"
    elif isinstance(error, BotError):
        text = f"⚠️ {error}"
    else:
        log.exception("Непредвиденная ошибка", exc_info=error)
        text = "💥 Что-то пошло не так. Попробуйте ещё раз или напишите /help."
    update = event.update
    target = update.message or (update.callback_query.message if update.callback_query else None)
    if update.callback_query:
        await update.callback_query.answer()
    if target:
        await target.answer(text)
    return True   # ошибка обработана
