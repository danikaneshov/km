import google.generativeai as genai
import config
from database import save_transaction, fetch_transactions, get_current_stock
import json
from datetime import datetime
import asyncio

if config.GEMINI_API_KEY:
    genai.configure(api_key=config.GEMINI_API_KEY)

def get_current_time_str():
    return datetime.now().isoformat()

# Tools definitions
def record_transaction_tool(tx_type: str, transactions_json: str):
    """
    Records one or multiple transactions.
    Args:
        tx_type: "in" for delivery (приход), "out" for expense (расход), "staff" for staff hookahs.
        transactions_json: A JSON string containing a list of transaction objects. Each object MUST have:
               - 'date': Date in ISO format (e.g. '2023-10-25T00:00:00').
               - 'items': A list of item dictionaries. Each item must have:
                          'category' (e.g. 'табак'), 'brand' (e.g. 'blackburn'), 
                          'quantity' (integer), 'unit' (e.g. 'шт'), 
                          'unit_size' (integer, for tobacco GRAMS per unit, for coals PIECES per pack).
    """
    pass

def fetch_history_tool(start_date: str = "", end_date: str = "", specific_day: int = 0, tx_type: str = ""):
    """
    Fetches transaction history based on dates.
    """
    pass

def get_stock_tool():
    """
    Returns the current inventory stock (how many of each item we have left).
    Call this when the user asks "сколько углей осталось", "что есть на складе", "остатки" etc.
    """
    pass

tools = [record_transaction_tool, fetch_history_tool, get_stock_tool]

async def process_user_message(user_message: str):
    if not config.GEMINI_API_KEY:
        return "Внимание: GEMINI_API_KEY не настроен."

    system_instruction = (
        "Ты - кальянный помощник Джарвис. Твоя задача - управлять складом (угли, табак) и считать кальяны.\n\n"
        "1. Запись массовых операций: Пользователь пишет 'угли краун 2 пачки по 72, табак бб 10шт по 200гр'. Вызывай record_transaction_tool (tx_type='in'). 72 для углей - кол-во углей в пачке, 200 - граммы табака.\n"
        "ВАЖНО: Если пользователь просит записать что-то за НЕСКОЛЬКО дней (например, 'стафф кальян с 1 по 10 сентября по одному в день'), ты ДОЛЖЕН создать в transactions_json 10 ОТДЕЛЬНЫХ объектов транзакций, каждый с разной датой ('date') от 1 до 10 сентября!\n"
        "ДЛЯ СТАФФ КАЛЬЯНОВ: Если пользователь пишет 'покурили стафф', вызывай record_transaction_tool с tx_type='staff' и добавь item: {\"category\": \"кальян\", \"brand\": \"стафф\", \"quantity\": 1, \"unit\": \"шт\"}. Это просто счетчик.\n\n"
        "2. Ответы: Отвечай коротко, КРАСИВО и ЧИТАБЕЛЬНО. Ты ДОЛЖЕН автоматически умножать количество на размер (граммы или штуки) и писать ИТОГО.\n"
        "ВАЖНОЕ ПРАВИЛО ФОРМАТИРОВАНИЯ: Для выделения жирным используй ТОЛЬКО HTML теги <b>текст</b>. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕН Markdown (никаких звездочек **)! В телеграме установлен HTML parse mode.\n"
        "Пример ответа:\n"
        "✅ <b>Записи успешно созданы!</b>\n"
        "• 💨 Кальян (стафф): 10 шт (разбито на 10 дней с 1 по 10 сентября)\n\n"
        "3. Склад: Вызывай get_stock_tool, красиво выведи список в наличии, и отдельной строкой количество выкуренных стафф кальянов (staff_hookahs_total).\n"
        "4. История: Вызывай fetch_history_tool. ТЫ ДОЛЖЕН вывести ВСЕ записи в виде списка дат (каждая дата с новой строки). ПРАВИЛО: Если в истории есть несколько записей за ОДИН И ТОТ ЖЕ ДЕНЬ, сложи их количество и выведи одной строкой (например: • 13.09.2026 - 2 шт). КАТЕГОРИЧЕСКИ ЗАПРЕЩАЕТСЯ просто писать общий текст-описание вместо списка дат!\n"
        "ВАЖНОЕ ПРАВИЛО ДЛЯ ПОДСЧЕТА ИТОГОВ: Нейросети плохо считают, поэтому в ответе на fetch_history_tool тебе приходит поле `exact_totals_calculated_by_system`. ВСЕГДА бери итоговую сумму ТОЛЬКО оттуда (tobacco_grams, coals_pieces)! НЕ ПЫТАЙСЯ складывать суммы самостоятельно!\n\n"
        f"Текущая дата: {get_current_time_str()}."
    )

    model = genai.GenerativeModel(
        model_name='gemini-flash-lite-latest',
        tools=tools,
        system_instruction=system_instruction
    )
    
    chat = model.start_chat(enable_automatic_function_calling=False)
    
    try:
        response = chat.send_message(user_message)
    except Exception as e:
        return f"Ошибка при запросе к Gemini: {e}"
        
    fc = None
    try:
        for part in response.parts:
            if part.function_call:
                fc = part.function_call
                break
    except Exception:
        pass
        
    if fc:
        fc_name = fc.name
        args = type(fc).to_dict(fc).get("args", {})
        api_response = {}
        
        if fc_name == "record_transaction_tool":
            tx_type = args.get("tx_type", "in")
            transactions_str = args.get("transactions_json", "[]")
            
            try:
                transactions_list = json.loads(transactions_str)
                recorded_ids = []
                
                # If they passed a single object by mistake, wrap it in a list
                if isinstance(transactions_list, dict):
                    transactions_list = [transactions_list]
                    
                for tx in transactions_list:
                    date = tx.get("date", get_current_time_str())
                    items = tx.get("items", [])
                    inserted_id = await save_transaction(date, items, user_message, tx_type)
                    recorded_ids.append(inserted_id)
                    
                api_response = {"result": "success", "recorded_count": len(recorded_ids)}
            except Exception as e:
                import logging
                logging.error(f"Error saving to DB: {e}", exc_info=True)
                api_response = {"result": "error", "error": str(e)}
                
        elif fc_name == "fetch_history_tool":
            try:
                records = await fetch_transactions(
                    args.get("start_date"), args.get("end_date"), 
                    args.get("specific_day"), args.get("tx_type")
                )
                
                # Compute exact totals to prevent LLM hallucinations
                totals = {"in": {"tobacco_grams": 0, "coals_pieces": 0},
                          "out": {"tobacco_grams": 0, "coals_pieces": 0},
                          "staff": {"hookahs": 0}}
                          
                for r in records:
                    t = r.get("type", "in")
                    if t not in totals:
                        totals[t] = {"tobacco_grams": 0, "coals_pieces": 0, "hookahs": 0}
                    for item in r.get("items", []):
                        cat = str(item.get("category", "")).lower()
                        qty = item.get("quantity", 0)
                        size = item.get("unit_size", 0) or 1
                        
                        if t == "staff" or "кальян" in cat:
                            totals["staff"]["hookahs"] += qty
                        elif "табак" in cat:
                            totals[t]["tobacco_grams"] += (qty * size)
                        elif "угл" in cat:
                            totals[t]["coals_pieces"] += (qty * size)

                api_response = {
                    "result": "success", 
                    "records_found": len(records), 
                    "records": records,
                    "exact_totals_calculated_by_system": totals
                }
            except Exception as e:
                api_response = {"result": "error", "error": str(e)}
                
        elif fc_name == "get_stock_tool":
            try:
                stock = await get_current_stock()
                api_response = {"result": "success", "stock": stock}
            except Exception as e:
                api_response = {"result": "error", "error": str(e)}

        # Small delay to prevent hitting limits if sending multiple rapid requests
        await asyncio.sleep(1)

        final_response = chat.send_message(
            genai.protos.Part(
                function_response=genai.protos.FunctionResponse(
                    name=fc_name,
                    response={"result": api_response}
                )
            )
        )
        return final_response.text

    return response.text
