"""
Модуль интеграции с Gemini AI.
Function Calling для автоматического определения действий из текста пользователя.
"""

import json
import logging

import google.generativeai as genai

from google.protobuf.json_format import MessageToDict

from config import GEMINI_API_KEY, GEMINI_MODEL, KNOWN_BRANDS, BRAND_ALIASES

log = logging.getLogger(__name__)


def _proto_to_dict(val):
    """Рекурсивно конвертирует protobuf/MapComposite объекты в обычные dict/list."""
    if hasattr(val, 'items'):
        return {k: _proto_to_dict(v) for k, v in val.items()}
    if hasattr(val, '__iter__') and not isinstance(val, (str, bytes)):
        return [_proto_to_dict(item) for item in val]
    return val

# ---------------------------------------------------------------------------
# Конфигурация Gemini
# ---------------------------------------------------------------------------
genai.configure(api_key=GEMINI_API_KEY)

# ---------------------------------------------------------------------------
# Описание функций (tools) для Function Calling
# ---------------------------------------------------------------------------
_tools = [
    genai.protos.Tool(
        function_declarations=[
            # --- Склад ---
            genai.protos.FunctionDeclaration(
                name="add_warehouse",
                description=(
                    "Записать приход товара на склад. Вызывай, когда пользователь "
                    "сообщает о поставке табака, углей или любых расходников."
                ),
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "items": genai.protos.Schema(
                            type=genai.protos.Type.ARRAY,
                            description="Список товаров прихода",
                            items=genai.protos.Schema(
                                type=genai.protos.Type.OBJECT,
                                properties={
                                    "brand": genai.protos.Schema(
                                        type=genai.protos.Type.STRING,
                                        description=f"Бренд или название товара. Для табака используй эталонные названия: {', '.join(KNOWN_BRANDS)}. Для углей пиши название как есть (например Cocoloco).",
                                    ),
                                    "flavor": genai.protos.Schema(
                                        type=genai.protos.Type.STRING,
                                        description="Вкус табака (если указан). Для углей не указывай.",
                                    ),
                                    "weight_g": genai.protos.Schema(
                                        type=genai.protos.Type.NUMBER,
                                        description="Вес в граммах. Используй ТОЛЬКО для табака.",
                                    ),
                                    "quantity_pcs": genai.protos.Schema(
                                        type=genai.protos.Type.INTEGER,
                                        description="Количество в штуках. Используй для углей и других штучных товаров.",
                                    ),
                                },
                                required=["brand"],
                            ),
                        ),
                        "notes": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Дополнительные заметки к приходу",
                        ),
                        "date": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Дата прихода в формате YYYY-MM-DD. Если не указана — используется сегодня.",
                        ),
                    },
                    required=["items"],
                ),
            ),
            # --- Излишек ---
            genai.protos.FunctionDeclaration(
                name="add_surplus",
                description=(
                    "Зачислить излишек — нескуренные гостями чаши. "
                    "Вызывай, когда мастер говорит: 'излишек N чаш', '+ N чаша', "
                    "'гость не докурил' и т.п."
                ),
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "bowls": genai.protos.Schema(
                            type=genai.protos.Type.INTEGER,
                            description="Количество нескуренных чаш",
                        ),
                        "date": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Дата излишка в формате YYYY-MM-DD. Если не указана — используется сегодня.",
                        ),
                    },
                    required=["bowls"],
                ),
            ),
            # --- Стафф ---
            genai.protos.FunctionDeclaration(
                name="add_staff",
                description=(
                    "Списать стафф-кальян — мастера покурили за счёт излишков. "
                    "Вызывай, когда мастер говорит: 'стафф', 'покурили стафф', "
                    "'- чаша' и т.п. ОБЯЗАТЕЛЬНО спроси у пользователя сколько "
                    "грамм табака ушло на стафф, прежде чем вызывать. Угли всегда 4."
                ),
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "tobacco_g": genai.protos.Schema(
                            type=genai.protos.Type.NUMBER,
                            description="Сколько грамм табака ушло на стафф",
                        ),
                        "date": genai.protos.Schema(
                            type=genai.protos.Type.STRING,
                            description="Дата стаффа в формате YYYY-MM-DD. Если не указана — используется сегодня.",
                        ),
                    },
                    required=["tobacco_g"],
                ),
            ),
            # --- Баланс ---
            genai.protos.FunctionDeclaration(
                name="get_balance",
                description=(
                    "Показать текущий баланс излишков. Вызывай, когда мастер "
                    "спрашивает: 'сколько излишков', 'баланс', 'что на счету' и т.п."
                ),
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={},
                ),
            ),
            # --- История ---
            genai.protos.FunctionDeclaration(
                name="get_history",
                description=(
                    "Показать историю излишков и стаффов за период. Вызывай, когда "
                    "мастер спрашивает: 'история за неделю', 'стата за 3 дня', "
                    "'покажи историю' и т.п."
                ),
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "days": genai.protos.Schema(
                            type=genai.protos.Type.INTEGER,
                            description="За сколько дней показать историю (по умолчанию 7)",
                        ),
                    },
                ),
            ),
            # --- История склада ---
            genai.protos.FunctionDeclaration(
                name="get_warehouse_history",
                description=(
                    "Показать историю приходов на склад. Вызывай, когда мастер "
                    "спрашивает: 'что приходило', 'история склада', 'приходы' и т.п."
                ),
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "days": genai.protos.Schema(
                            type=genai.protos.Type.INTEGER,
                            description="За сколько дней показать историю (по умолчанию 30)",
                        ),
                    },
                ),
            ),
        ]
    )
]

# ---------------------------------------------------------------------------
# Справочник сленга для системного промпта
# ---------------------------------------------------------------------------
_brand_aliases_text = ", ".join(f"{k} → {v}" for k, v in BRAND_ALIASES.items())

SYSTEM_PROMPT = f"""Ты — бот-помощник кальянного мастера. Ты управляешь складом и балансом излишков/стаффов.

ПРАВИЛА ПОВЕДЕНИЯ:
1. По рабочим вопросам (склад, излишки, стафф, баланс, приходы) — отвечай КОРОТКО, чётко, по делу. Никакой воды.
2. Если пользователь пишет что-то НЕ связанное с работой (приветствия, болтовня, вопросы про погоду и т.д.) — отвечай АГРЕССИВНО-ГРУБО С МАТОМ, заставляя вернуться к рабочим вопросам. Ты не для болтовни.
3. Используй ТОЛЬКО HTML-теги для форматирования (<b>, <i>, <code>). НИКАКОГО Markdown.

СПРАВОЧНИК БРЕНДОВ (сленг → эталон):
{_brand_aliases_text}

Полный список эталонных брендов: {', '.join(KNOWN_BRANDS)}

ШАБЛОН ЧАШИ (ИЗЛИШЕК):
1 чаша = 23 грамм табака + 5 углей

ШАБЛОН СТАФФА:
Количество табака ВСЕГДА спрашивается у пользователя, а угли ВСЕГДА 4 штуки (за 1 стафф-чашу).

ВАЖНО:
- Когда пользователь говорит об излишке — вызови функцию add_surplus.
- Когда пользователь говорит о стаффе — вызови функцию add_staff.
- Когда пользователь сообщает о приходе на склад — вызови функцию add_warehouse.
- Когда спрашивает баланс — вызови get_balance.
- Когда спрашивает историю — вызови get_history или get_warehouse_history.
- Всегда исправляй сленговые названия брендов на эталонные при записи.
- Если пользователь указывает конкретную дату (вчера, 10 сентября, позавчера и т.д.) — передай её в параметр date в формате YYYY-MM-DD. Если дату не указал — НЕ передавай параметр date, будет использована сегодняшняя.
- Если тебе не хватает данных для вызова функции — спроси коротко.
"""

# ---------------------------------------------------------------------------
# Хранилище чатов (per-user history)
# ---------------------------------------------------------------------------
_chat_sessions: dict[int, genai.ChatSession] = {}


def _get_or_create_chat(user_id: int) -> genai.ChatSession:
    """Возвращает или создаёт чат-сессию для пользователя."""
    if user_id not in _chat_sessions:
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            tools=_tools,
            system_instruction=SYSTEM_PROMPT,
        )
        _chat_sessions[user_id] = model.start_chat(enable_automatic_function_calling=False)
    return _chat_sessions[user_id]


async def process_message(user_id: int, text: str) -> tuple[str | None, list[dict]]:
    """
    Отправляет текст пользователя в Gemini и возвращает:
    - response_text: текстовый ответ бота (или None)
    - function_calls: список словарей {"name": ..., "args": {...}}
    """
    chat = _get_or_create_chat(user_id)

    try:
        response = await chat.send_message_async(text)
    except Exception as e:
        log.error("Gemini error: %s", e)
        # Сбрасываем сессию при ошибке
        _chat_sessions.pop(user_id, None)
        return "⚠️ Ошибка AI, попробуй ещё раз.", []

    # Разбираем ответ
    function_calls = []
    response_text = None

    for part in response.parts:
        if fn := part.function_call:
            call_args = _proto_to_dict(fn.args) if fn.args else {}
            function_calls.append({"name": fn.name, "args": call_args})
        elif part.text:
            response_text = part.text

    return response_text, function_calls


async def send_function_result(
    user_id: int, fn_name: str, result: dict
) -> tuple[str | None, list[dict]]:
    """
    Отправляет результат выполнения функции обратно в Gemini,
    чтобы получить финальный текстовый ответ.
    """
    chat = _get_or_create_chat(user_id)

    response_part = genai.protos.Part(
        function_response=genai.protos.FunctionResponse(
            name=fn_name,
            response={"result": result},
        )
    )

    try:
        response = await chat.send_message_async(response_part)
    except Exception as e:
        log.error("Gemini function result error: %s", e)
        return "✅ Записано.", []

    function_calls = []
    response_text = None

    for part in response.parts:
        if fn := part.function_call:
            call_args = _proto_to_dict(fn.args) if fn.args else {}
            function_calls.append({"name": fn.name, "args": call_args})
        elif part.text:
            response_text = part.text

    return response_text, function_calls
