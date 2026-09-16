"""
Авторизация: middleware для проверки доступа и обработка секретной фразы.
"""

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Router, types
from aiogram.types import TelegramObject

from config import ALLOWED_TELEGRAM_ID, SECRET_PHRASE
from db import is_admin, add_admin

log = logging.getLogger(__name__)

router = Router(name="auth")


# ---------------------------------------------------------------------------
# Middleware: проверка авторизации
# ---------------------------------------------------------------------------
class AuthMiddleware(BaseMiddleware):
    """Пропускает только авторизованных пользователей."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Работаем только с Message
        if not isinstance(event, types.Message):
            return await handler(event, data)

        message: types.Message = event
        user_id = message.from_user.id if message.from_user else None

        if user_id is None:
            return  # Игнорируем

        # --- Проверка секретной фразы ---
        if message.text and message.text.strip() == SECRET_PHRASE:
            bot: Bot = data["bot"]
            # Удаляем сообщение с фразой
            try:
                await bot.delete_message(
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                )
            except Exception as e:
                log.warning("Не удалось удалить сообщение с секретной фразой: %s", e)

            # Добавляем в admins
            await add_admin(user_id)
            log.info("Новый авторизованный пользователь: %s", user_id)

            # Отправляем подтверждение
            try:
                await bot.send_message(
                    chat_id=message.chat.id,
                    text="🔓 <b>Доступ открыт.</b> Теперь ты в деле.",
                    parse_mode="HTML",
                )
            except Exception as e:
                log.warning("Не удалось отправить подтверждение авторизации: %s", e)

            return  # Не передаём дальше

        # --- Проверка: основной аккаунт или админ ---
        if user_id == ALLOWED_TELEGRAM_ID:
            return await handler(event, data)

        if await is_admin(user_id):
            return await handler(event, data)

        # Неавторизованный пользователь — игнорируем
        return
