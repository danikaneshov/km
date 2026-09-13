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
def record_transaction_tool(tx_type: str, date: str, items_json: str):
    """
    Records a new transaction (either a delivery/приход or an expense/расход).
    Args:
        tx_type: "in" for delivery (приход), "out" for expense (расход, списание).
        date: Date in ISO format (e.g. '2023-10-25T00:00:00'). Use current date if not specified.
        items_json: A JSON string containing a list of item dictionaries. Each item must have:
               - 'category': category (e.g. 'табак', 'угли')
               - 'brand': brand name (e.g. 'blackburn', 'краун')
               - 'quantity': number of units (integer)
               - 'unit': unit type (e.g. 'пачка', 'шт', 'кг')
               - 'unit_size': integer, for tobacco GRAMS per unit, for coals PIECES per pack.
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
        "1. Запись: Пользователь пишет 'угли краун 2 пачки по 72, табак бб 10шт по 200гр'. Вызывай record_transaction_tool (tx_type='in' для прихода, 'out' для списания). 72 для углей - кол-во углей в пачке, 200 - граммы табака. items_json должен быть валидным JSON!\n"
        "ВАЖНО ДЛЯ СТАФФ КАЛЬЯНОВ: Если пользователь пишет 'покурили стафф', 'стафф 2 кальяна', вызывай record_transaction_tool с tx_type='staff' и items_json=[{\"category\": \"кальян\", \"brand\": \"стафф\", \"quantity\": 2 (или сколько указано), \"unit\": \"шт\"}]. Это просто записывает количество, не списывая склад.\n\n"
        "2. Ответы: Отвечай коротко, КРАСИВО и ЧИТАБЕЛЬНО. Ты ДОЛЖЕН автоматически умножать количество на размер (граммы или штуки) и писать ИТОГО в штуках или граммах!\n"
        "Пример идеального ответа для прихода/списания:\n"
        "✅ **Приход успешно записан!**\n"
        "• 🧊 Угли Crown: 144 шт (2 пачки по 72)\n"
        "• 🍃 Табак BlackBurn: 2000 гр (10 шт по 200)\n"
        "Пример идеального ответа для стафф кальянов:\n"
        "✅ **Стафф кальян записан!** 💨\n\n"
        "3. Склад: Пользователь может спросить 'остатки' или 'сколько стаффов'. Вызывай get_stock_tool, и затем красиво выведи список того, что есть в наличии, а также отдельной строкой количество выкуренных стафф кальянов (из staff_hookahs_total).\n"
        "4. История: Пользователь может просить историю приходов ('что было 25 числа'). Вызывай fetch_history_tool и выводи красиво с датами.\n\n"
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
            date = args.get("date", get_current_time_str())
            items_str = args.get("items_json", "[]")
            try:
                items = json.loads(items_str)
            except json.JSONDecodeError:
                items = []
            tx_type = args.get("tx_type", "in")
            
            try:
                inserted_id = await save_transaction(date, items, user_message, tx_type)
                api_response = {"result": "success", "recorded_items": items}
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
                api_response = {"result": "success", "records_found": len(records), "records": records}
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
