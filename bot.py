"""Лабораторная работа №4. Вариант 7 - Telegram-бот «Фильмы».

Запуск: python bot.py   (токен бота берётся из файла .env или переменной BOT_TOKEN)
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.types import BotCommand

from movies.api import MovieApi
from movies.handlers import router
from movies.storage import UserStore

BASE_DIR = Path(__file__).parent
ENV_FILE = BASE_DIR / ".env"
USERS_FILE = BASE_DIR / "users.json"

COMMANDS = [
    BotCommand(command="start", description="Начать"),
    BotCommand(command="search", description="Найти фильм: /search Матрица"),
    BotCommand(command="top", description="Топ фильмов iTunes"),
    BotCommand(command="random", description="Случайный фильм"),
    BotCommand(command="favorites", description="Избранное"),
    BotCommand(command="history", description="Последние запросы"),
    BotCommand(command="settings", description="Настройки"),
    BotCommand(command="help", description="Помощь"),
]


def read_token() -> str:
    """Токен - секрет, поэтому он не в коде, а в файле .env (его нет на GitHub)."""
    token = os.getenv("BOT_TOKEN", "")
    if not token and ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("BOT_TOKEN="):
                token = line.split("=", 1)[1].strip()
    if not token or ":" not in token:
        sys.exit("Не найден токен бота. Создайте файл .env со строкой BOT_TOKEN=... "
                 "(образец - .env.example)")
    return token


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    store = UserStore(USERS_FILE)
    if store.warning:
        logging.warning(store.warning)
    api = MovieApi()
    bot = Bot(read_token(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    # api и store будут переданы в обработчики автоматически (по имени параметра)
    dp = Dispatcher(api=api, store=store)
    dp.include_router(router)
    try:
        me = await bot.get_me()
        logging.info("Бот @%s запущен. Остановить: Ctrl+C", me.username)
        await bot.set_my_commands(COMMANDS)   # меню команд в Telegram
        await dp.start_polling(bot)
    except TelegramUnauthorizedError:
        sys.exit("Telegram не принял токен - проверьте строку BOT_TOKEN в файле .env")
    finally:
        await api.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")
