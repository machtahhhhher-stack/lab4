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
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError
from aiogram.types import BotCommand

try:
    # ошибки прокси (если Telegram открывается только через VPN-прокси)
    from aiohttp_socks import ProxyConnectionError, ProxyError, ProxyTimeoutError
    PROXY_ERRORS: tuple[type[Exception], ...] = (ProxyConnectionError, ProxyError, ProxyTimeoutError)
except ImportError:      # библиотека не установлена - значит, прокси и не используется
    PROXY_ERRORS = ()

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


def read_setting(name: str) -> str:
    """Значение из переменной окружения или из файла .env (строка ИМЯ=значение)."""
    value = os.getenv(name, "")
    if not value and ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{name}="):
                value = line.split("=", 1)[1].strip()
    return value


def read_token() -> str:
    """Токен - секрет, поэтому он не в коде, а в файле .env (его нет на GitHub)."""
    token = read_setting("BOT_TOKEN")
    if not token or ":" not in token:
        sys.exit("Не найден токен бота. Создайте файл .env со строкой BOT_TOKEN=... "
                 "(образец - .env.example)")
    return token


def make_session() -> AiohttpSession | None:
    """Если Telegram в сети заблокирован, бот может ходить к нему через прокси
    от VPN-программы: строка PROXY=socks5://127.0.0.1:10808 в файле .env."""
    proxy = read_setting("PROXY")
    if not proxy:
        return None   # обычное прямое подключение
    logging.info("Подключение к Telegram через прокси %s", proxy)
    return AiohttpSession(proxy=proxy)


NO_CONNECTION = (
    "Нет связи с серверами Telegram (api.telegram.org).\n"
    "  * Проверьте интернет.\n"
    "  * Если Telegram у вас работает только через VPN - включите в VPN-программе режим\n"
    "    «весь трафик» / TUN / «VPN-режим», или впишите в файл .env строку с прокси, например\n"
    "    PROXY=socks5://127.0.0.1:10808  (порт смотрите в настройках VPN-программы).\n"
    "  * Или раздайте интернет с телефона."
)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    store = UserStore(USERS_FILE)
    if store.warning:
        logging.warning(store.warning)
    api = MovieApi()
    bot = Bot(read_token(), session=make_session(),
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
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
    except (TelegramNetworkError, OSError, *PROXY_ERRORS) as error:
        # нет интернета, Telegram заблокирован или прокси не отвечает
        sys.exit(f"{NO_CONNECTION}\n\nПодробности: {error}")
    finally:
        await api.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")
