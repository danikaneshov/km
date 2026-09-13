import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties

import config
from ai import process_user_message

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

dp = Dispatcher()

# Optional: simple middleware or filter for ALLOWED_TELEGRAM_ID
def is_allowed(user_id: int) -> bool:
    if not config.ALLOWED_TELEGRAM_ID:
        return True # If not set, allow everyone (or you could choose to deny everyone)
    return user_id == config.ALLOWED_TELEGRAM_ID

@dp.message(CommandStart())
async def command_start_handler(message: types.Message) -> None:
    if not is_allowed(message.from_user.id):
        await message.answer("Извините, у вас нет доступа к этому боту.")
        return
        
    await message.answer(
        "Привет! Я твой кальянный Джарвис 🤖💨\n\n"
        "Пиши мне приходы в любом формате. Например:\n"
        "«угли краун 2 пачки по 72 угля, табак бб 10шт по 200гр»\n\n"
        "Или спрашивай про историю:\n"
        "«покажи все приходы за этот месяц»"
    )

@dp.message()
async def message_handler(message: types.Message) -> None:
    if not is_allowed(message.from_user.id):
        # Ignore or send a warning
        return
        
    try:
        # Send a typing action
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        
        # Process via Gemini
        response_text = await process_user_message(message.text)
        
        await message.answer(response_text)
    except Exception as e:
        logging.error(f"Error handling message: {e}")
        await message.answer(f"Упс, произошла ошибка: {e}")

async def main() -> None:
    if not config.TELEGRAM_TOKEN:
        logging.error("TELEGRAM_TOKEN is not set in environment variables.")
        return
        
    bot = Bot(
        token=config.TELEGRAM_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
