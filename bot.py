"""
Точка входа: инициализация бота, подключение роутеров, запуск polling.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from config import TELEGRAM_TOKEN, ALLOWED_TELEGRAM_ID
from db import ensure_owner
from handlers.auth import AuthMiddleware
from handlers import messages as msg_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger(__name__)


async def main() -> None:
    log.info("Запуск бота...")

    bot = Bot(
        token=TELEGRAM_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher()

    # Middleware авторизации — применяется ко всем сообщениям
    dp.message.middleware(AuthMiddleware())

    # Роутеры
    dp.include_router(msg_handlers.router)

    # Гарантируем, что основной аккаунт в admins
    await ensure_owner(ALLOWED_TELEGRAM_ID)

    log.info("Бот запущен. Ожидание сообщений...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
