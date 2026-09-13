import asyncio
import logging
import sys
import os
import uuid

from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.types import FSInputFile

import config
from ai import process_user_message

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

dp = Dispatcher()

# Optional: simple middleware or filter for ALLOWED_TELEGRAM_ID
def is_allowed(user_id: int) -> bool:
    if not config.ALLOWED_TELEGRAM_ID:
        return True 
    return user_id == config.ALLOWED_TELEGRAM_ID

@dp.message(CommandStart())
async def command_start_handler(message: types.Message) -> None:
    if not is_allowed(message.from_user.id):
        await message.answer("Извините, у вас нет доступа к этому боту.")
        return
        
    await message.answer(
        "Привет! Я твой кальянный Джарвис 2.0 🤖💨\n\n"
        "Пиши мне приходы, расходы, или отправляй голосовые сообщения!\n"
        "Например:\n"
        "«угли краун 2 пачки по 72 угля»\n\n"
        "Или спрашивай:\n"
        "«покажи график стафф кальянов»"
    )

async def handle_ai_response(message: types.Message, ai_res: dict):
    text = ai_res.get("text", "")
    image_path = ai_res.get("image")
    
    if image_path and os.path.exists(image_path):
        photo = FSInputFile(image_path)
        await message.answer_photo(photo=photo, caption=text)
        # Clean up chart file
        try:
            os.remove(image_path)
        except Exception:
            pass
    else:
        if text:
            await message.answer(text)

@dp.message(F.voice)
async def voice_handler(message: types.Message, bot: Bot) -> None:
    if not is_allowed(message.from_user.id):
        return
        
    try:
        await bot.send_chat_action(chat_id=message.chat.id, action="upload_voice")
        
        # Download voice file
        file_id = message.voice.file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path
        
        local_filename = f"voice_{uuid.uuid4().hex[:8]}.ogg"
        await bot.download_file(file_path, local_filename)
        
        # Process via Gemini
        ai_res = await process_user_message(
            user_id=message.from_user.id, 
            voice_file_path=local_filename
        )
        
        await handle_ai_response(message, ai_res)
        
        # Cleanup voice file
        try:
            os.remove(local_filename)
        except Exception:
            pass
            
    except Exception as e:
        import html
        logging.error(f"Error handling voice message: {e}", exc_info=True)
        await message.answer(f"Упс, произошла ошибка: {html.escape(str(e))}")

@dp.message(F.text)
async def message_handler(message: types.Message) -> None:
    if not is_allowed(message.from_user.id):
        return
        
    try:
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        
        ai_res = await process_user_message(
            user_id=message.from_user.id,
            user_message=message.text
        )
        
        await handle_ai_response(message, ai_res)
        
    except Exception as e:
        import html
        logging.error(f"Error handling text message: {e}", exc_info=True)
        await message.answer(f"Упс, произошла ошибка: {html.escape(str(e))}")

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
