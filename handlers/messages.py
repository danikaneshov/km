"""
Основной обработчик сообщений: текст + голос → AI → function calls → ответ.
"""

import io
import json
import logging
from datetime import datetime

from aiogram import Bot, Router, types, F
from aiogram.enums import ContentType

from config import LOG_CHANNEL_ID, SURPLUS_TOBACCO_GRAMS, SURPLUS_COALS_COUNT, STAFF_COALS_COUNT
from ai import process_message, send_function_result
import db

log = logging.getLogger(__name__)

router = Router(name="messages")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _send_log(bot: Bot, text: str) -> None:
    """Отправляет запись в лог-канал."""
    if not LOG_CHANNEL_ID:
        return
    try:
        await bot.send_message(
            chat_id=LOG_CHANNEL_ID,
            text=text,
            parse_mode="HTML",
        )
    except Exception as e:
        log.warning("Не удалось отправить в лог-канал: %s", e)


def _format_warehouse_items(items: list[dict]) -> str:
    """Форматирует список товаров прихода в строку."""
    lines = []
    for item in items:
        parts = [f"<b>{item.get('brand', '?')}</b>"]
        if flavor := item.get("flavor"):
            parts.append(f"— {flavor}")
        if weight := item.get("weight_g"):
            parts.append(f"({weight}г)")
        if qty := item.get("quantity_pcs"):
            parts.append(f"({qty} шт)")
        lines.append(" ".join(parts))
    return "\n".join(lines) if lines else "—"


def _format_balance(balance: dict) -> str:
    """Форматирует баланс в строку."""
    return (
        f"📊 <b>Текущий баланс излишков:</b>\n"
        f"  🍵 Чаш: <b>{balance['bowls']}</b>\n"
        f"  🌿 Табак: <b>{balance['tobacco_g']}г</b>\n"
        f"  🔥 Угли: <b>{balance['coals']} шт</b>"
    )


def _format_history(history: list[dict]) -> str:
    """Форматирует историю по дням."""
    if not history:
        return "📭 За этот период записей нет."

    # Группируем по дате
    days: dict[str, dict] = {}
    for entry in history:
        date = entry["_id"]["date"]
        entry_type = entry["_id"]["type"]

        if date not in days:
            days[date] = {"surplus": 0, "staff": 0}
        days[date][entry_type] = entry["total_bowls"]

    lines = ["📋 <b>История по дням:</b>\n"]
    for date, data in sorted(days.items()):
        surplus = data.get("surplus", 0)
        staff = data.get("staff", 0)
        lines.append(
            f"  📅 <b>{date}</b>: "
            f"излишек <b>+{surplus}</b> чаш, "
            f"стафф <b>-{staff}</b> чаш"
        )

    return "\n".join(lines)


def _format_warehouse_history(history: list[dict]) -> str:
    """Форматирует историю приходов на склад."""
    if not history:
        return "📭 Приходов за этот период нет."

    # Считаем итоги
    total_tobacco_g = 0
    total_coals_pcs = 0
    for entry in history:
        for item in entry.get("items", []):
            total_tobacco_g += item.get("weight_g", 0) or 0
            total_coals_pcs += item.get("quantity_pcs", 0) or 0

    lines = [
        "🏭 <b>История приходов на склад:</b>\n",
        f"📊 <b>Итого:</b> 🌿 табак <b>{total_tobacco_g}г</b>, 🔥 угли <b>{total_coals_pcs} шт</b>\n",
    ]

    for entry in history:
        date = entry["date"].strftime("%Y-%m-%d %H:%M")
        items_text = _format_warehouse_items(entry.get("items", []))
        lines.append(f"  📅 <b>{date}</b>\n{items_text}")
        if notes := entry.get("notes"):
            lines.append(f"  💬 {notes}")
        lines.append("")

    return "\n".join(lines)


def _parse_date(date_str: str | None) -> datetime | None:
    """Парсит дату из строки YYYY-MM-DD. Возвращает None если не указана."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Выполнение function calls
# ---------------------------------------------------------------------------
async def _execute_function(
    fn_name: str, fn_args: dict, user_id: int, bot: Bot
) -> dict:
    """Выполняет функцию и возвращает результат."""

    if fn_name == "add_warehouse":
        items = fn_args.get("items", [])
        notes = fn_args.get("notes", "")
        date = _parse_date(fn_args.get("date"))
        doc = await db.add_warehouse_entry(items, notes, date)
        date_label = fn_args.get("date", "сегодня")

        items_text = _format_warehouse_items(items)
        await _send_log(
            bot,
            f"🏭 <b>Приход на склад</b> (📅 {date_label})\n"
            f"👤 <code>{user_id}</code>\n"
            f"{items_text}\n"
            f"{f'💬 {notes}' if notes else ''}",
        )
        return {"status": "ok", "message": f"Приход записан: {len(items)} позиций, дата: {date_label}"}

    elif fn_name == "add_surplus":
        bowls = int(fn_args.get("bowls", 1))
        date = _parse_date(fn_args.get("date"))
        doc = await db.add_surplus(bowls, user_id, date)
        tobacco = bowls * SURPLUS_TOBACCO_GRAMS
        coals = bowls * SURPLUS_COALS_COUNT
        date_label = fn_args.get("date", "сегодня")

        await _send_log(
            bot,
            f"➕ <b>Излишек</b> (📅 {date_label})\n"
            f"👤 <code>{user_id}</code>\n"
            f"🍵 Чаш: <b>{bowls}</b> (+{tobacco}г табака, +{coals} углей)",
        )
        return {
            "status": "ok",
            "bowls": bowls,
            "tobacco_g": tobacco,
            "coals": coals,
        }

    elif fn_name == "add_staff":
        tobacco = float(fn_args.get("tobacco_g", 0))
        coals = STAFF_COALS_COUNT
        date = _parse_date(fn_args.get("date"))
        doc = await db.add_staff(tobacco, user_id, date)
        date_label = fn_args.get("date", "сегодня")

        await _send_log(
            bot,
            f"➖ <b>Стафф</b> (📅 {date_label})\n"
            f"👤 <code>{user_id}</code>\n"
            f"🌿 Табак: <b>{tobacco}г</b>, 🔥 Угли: <b>{coals} шт</b>",
        )
        return {
            "status": "ok",
            "tobacco_g": tobacco,
            "coals": coals,
        }

    elif fn_name == "get_balance":
        balance = await db.get_balance()
        return {
            "status": "ok",
            "bowls": balance["bowls"],
            "tobacco_g": balance["tobacco_g"],
            "coals": balance["coals"],
            "formatted": _format_balance(balance),
        }

    elif fn_name == "get_history":
        days = int(fn_args.get("days", 7))
        history = await db.get_history(days)
        return {
            "status": "ok",
            "formatted": _format_history(history),
        }

    elif fn_name == "get_warehouse_history":
        days = int(fn_args.get("days", 30))
        history = await db.get_warehouse_history(days)
        return {
            "status": "ok",
            "formatted": _format_warehouse_history(history),
        }

    return {"status": "error", "message": f"Неизвестная функция: {fn_name}"}


# ---------------------------------------------------------------------------
# Обработка AI-ответа (рекурсивно выполняет function calls)
# ---------------------------------------------------------------------------
async def _handle_ai_response(
    user_id: int,
    response_text: str | None,
    function_calls: list[dict],
    bot: Bot,
    message: types.Message,
    depth: int = 0,
) -> None:
    """Обрабатывает ответ AI: выполняет function calls, отправляет текст."""
    if depth > 5:
        await message.answer("⚠️ Слишком много вызовов, останавливаюсь.", parse_mode="HTML")
        return

    if function_calls:
        for fc in function_calls:
            fn_name = fc["name"]
            fn_args = fc["args"]
            log.info("Function call: %s(%s)", fn_name, fn_args)

            result = await _execute_function(fn_name, fn_args, user_id, bot)

            # Отправляем результат обратно в AI
            final_text, more_calls = await send_function_result(
                user_id, fn_name, result
            )

            if more_calls:
                await _handle_ai_response(
                    user_id, final_text, more_calls, bot, message, depth + 1
                )
            elif final_text:
                await message.answer(final_text, parse_mode="HTML")
            else:
                # AI не вернул текст — формируем сами
                if "formatted" in result:
                    await message.answer(result["formatted"], parse_mode="HTML")
                else:
                    await message.answer("✅ Готово.", parse_mode="HTML")

    elif response_text:
        await message.answer(response_text, parse_mode="HTML")


# ---------------------------------------------------------------------------
# Обработчик текстовых сообщений
# ---------------------------------------------------------------------------
@router.message(F.content_type == ContentType.TEXT)
async def on_text_message(message: types.Message, bot: Bot) -> None:
    """Обработка текстовых сообщений."""
    user_id = message.from_user.id
    text = message.text.strip()

    if not text:
        return

    response_text, function_calls = await process_message(user_id, text)
    await _handle_ai_response(user_id, response_text, function_calls, bot, message)


# ---------------------------------------------------------------------------
# Обработчик голосовых сообщений
# ---------------------------------------------------------------------------
@router.message(F.content_type == ContentType.VOICE)
async def on_voice_message(message: types.Message, bot: Bot) -> None:
    """Обработка голосовых сообщений: скачиваем → отправляем в Gemini."""
    user_id = message.from_user.id

    try:
        # Скачиваем голосовое сообщение
        voice = message.voice
        file = await bot.get_file(voice.file_id)
        file_bytes = io.BytesIO()
        await bot.download_file(file.file_path, file_bytes)
        file_bytes.seek(0)

        # Отправляем аудио в Gemini как inline data
        import google.generativeai as genai
        from ai import _get_or_create_chat, SYSTEM_PROMPT, _tools
        from config import GEMINI_MODEL

        # Создаём одноразовый запрос с аудио
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            tools=_tools,
            system_instruction=SYSTEM_PROMPT,
        )

        audio_part = genai.protos.Part(
            inline_data=genai.protos.Blob(
                mime_type="audio/ogg",
                data=file_bytes.read(),
            )
        )

        text_part = genai.protos.Part(
            text="Пользователь отправил голосовое сообщение. Расшифруй его и выполни запрос."
        )

        response = await model.generate_content_async(
            [text_part, audio_part],
            tools=_tools,
        )

        # Разбираем ответ
        function_calls = []
        response_text = None

        for part in response.parts:
            if fn := part.function_call:
                call_args = dict(fn.args) if fn.args else {}
                function_calls.append({"name": fn.name, "args": call_args})
            elif part.text:
                response_text = part.text

        # Для голосовых function calls обрабатываем отдельно
        if function_calls:
            for fc in function_calls:
                result = await _execute_function(fc["name"], fc["args"], user_id, bot)
                if "formatted" in result:
                    await message.answer(result["formatted"], parse_mode="HTML")
                else:
                    await message.answer("✅ Готово.", parse_mode="HTML")
        elif response_text:
            await message.answer(response_text, parse_mode="HTML")
        else:
            await message.answer("🤷 Не смог разобрать голосовое.", parse_mode="HTML")

    except Exception as e:
        log.error("Voice processing error: %s", e)
        await message.answer(
            "⚠️ Не удалось обработать голосовое сообщение.", parse_mode="HTML"
        )
