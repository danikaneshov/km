import google.generativeai as genai
import config
from database import save_transaction, fetch_transactions, get_current_stock
from charts import draw_pie_chart, draw_bar_chart
import json
from datetime import datetime
import asyncio
import os
from collections import defaultdict

if config.GEMINI_API_KEY:
    genai.configure(api_key=config.GEMINI_API_KEY)
    os.environ["GEMINI_API_KEY"] = config.GEMINI_API_KEY

def get_current_time_str():
    return datetime.now().isoformat()

# Tools definitions
def record_transaction_tool(tx_type: str, transactions_json: str):
    """
    Records one or multiple transactions.
    Args:
        tx_type: "in" for delivery (приход), "out" for expense (расход), "staff" for staff hookahs.
        transactions_json: JSON string with a list of transaction objects. Each MUST have:
               - 'date': Date in ISO format (e.g. '2023-10-25T00:00:00').
               - 'items': A list of item dicts with:
                          'category' (e.g. 'табак'), 'brand' (e.g. 'BlackBurn'), 
                          'quantity' (integer), 'unit' (e.g. 'шт'), 
                          'unit_size' (integer).
    """
    pass

def fetch_history_tool(start_date: str = "", end_date: str = "", specific_day: int = 0, tx_type: str = ""):
    """
    Fetches transaction history based on dates.
    """
    pass

def get_stock_tool():
    """
    Returns current inventory stock.
    """
    pass

def generate_chart_tool(chart_type: str):
    """
    Generates a visual chart for the user.
    Args:
        chart_type: 
            'top_tobacco_stock' (pie chart of current tobacco stock weights), 
            'staff_history' (bar chart of staff hookahs grouped by day for the last 30 days)
    """
    pass

tools = [record_transaction_tool, fetch_history_tool, get_stock_tool, generate_chart_tool]

# Memory storage: mapping user_id -> chat session
sessions = {}

async def process_user_message(user_id: int, user_message: str = "", voice_file_path: str = None) -> dict:
    if not config.GEMINI_API_KEY:
        return {"text": "Внимание: GEMINI_API_KEY не настроен."}

    system_instruction = (
        "Ты - кальянный помощник Джарвис 2.0. Твоя задача - управлять складом (угли, табак) и считать кальяны.\n\n"
        "=== СПРАВОЧНИК БРЕНДОВ ===\n"
        "ВСЕГДА исправляй опечатки и сленг (бб, дс, мастхэв, краун) на эталонные названия перед записью в базу. "
        "Эталонный список: BlackBurn, MustHave, DarkSide, Crown, Cocoloco, Sebero, Vkuss, Jam, Hell, Overdose, Sarma.\n\n"
        "=== ЗАПИСИ ===\n"
        "1. Массовые операции: Если пишут за несколько дней ('с 1 по 10 сентября'), создавай в transactions_json 10 ОТДЕЛЬНЫХ объектов транзакций, каждый с разной датой!\n"
        "2. Стафф кальяны: Вызывай record_transaction_tool (tx_type='staff') и добавь item: {\"category\": \"кальян\", \"brand\": \"стафф\", \"quantity\": 1, \"unit\": \"шт\"}.\n\n"
        "=== ОТВЕТЫ ===\n"
        "Отвечай коротко, КРАСИВО и ЧИТАБЕЛЬНО. Ты ДОЛЖЕН автоматически умножать количество на размер (граммы или штуки) и писать ИТОГО.\n"
        "ПО УМОЛЧАНИЮ (если не просят подробно): Выводи табак (в килограммах/граммах) и угли (в штуках) ТОЛЬКО общими суммами, без разбивки по брендам. Расписывай по брендам ТОЛЬКО если пользователь прямо попросит 'подробно' или 'какие бренды'.\n"
        "ВАЖНО: Для выделения жирным используй ТОЛЬКО HTML теги <b>текст</b>. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕН Markdown (никаких звездочек **)! В телеграме установлен HTML parse mode.\n\n"
        "=== ИСТОРИЯ И МАТЕМАТИКА ===\n"
        "Если просят историю, вызывай fetch_history_tool. Выводи в виде списка дат. НИКАКОГО ОБЩЕГО ТЕКСТА вместо списка!\n"
        "ВНИМАНИЕ: Тебе в `exact_totals_calculated_by_system` приходит ИДЕАЛЬНАЯ СУММА. ВСЕГДА бери итоговую сумму ТОЛЬКО оттуда (tobacco_grams, coals_pieces)! НЕ ПЫТАЙСЯ считать сам!\n\n"
        "=== ГРАФИКИ ===\n"
        "Если просят график или визуальную статистику, вызывай generate_chart_tool. В ответ ты получишь chart_file.\n\n"
        f"Текущая дата: {get_current_time_str()}."
    )

    if user_id not in sessions:
        model = genai.GenerativeModel(
            model_name='gemini-flash-lite-latest',
            tools=tools,
            system_instruction=system_instruction
        )
        sessions[user_id] = model.start_chat(enable_automatic_function_calling=False)
        
    chat = sessions[user_id]
    
    # Prepare message parts
    parts = []
    if voice_file_path and os.path.exists(voice_file_path):
        # Pass voice inline as bytes instead of using File API
        with open(voice_file_path, "rb") as f:
            audio_bytes = f.read()
        parts.append({"mime_type": "audio/ogg", "data": audio_bytes})
        
    if user_message:
        parts.append(user_message)
        
    if not parts:
        return {"text": "Пустое сообщение."}

    image_to_send = None

    try:
        response = chat.send_message(parts)
    except Exception as e:
        return {"text": f"Ошибка при запросе к Gemini: {e}"}
        
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

        elif fc_name == "generate_chart_tool":
            try:
                chart_type = args.get("chart_type", "")
                if chart_type == "top_tobacco_stock":
                    # Get stock, filter tobacco, sort by weight
                    stock_res = await get_current_stock()
                    stock_items = stock_res.get("stock", [])
                    tobacco = defaultdict(int)
                    
                    for item in stock_items:
                        if "табак" in item["category"].lower():
                            tobacco[item["brand"].capitalize()] += item["quantity"] * (item["unit_size"] or 1)
                            
                    if not tobacco:
                        api_response = {"result": "error", "error": "Нет данных по табаку на складе."}
                    else:
                        labels = list(tobacco.keys())
                        sizes = list(tobacco.values())
                        image_to_send = draw_pie_chart(labels, sizes, "Остатки табака на складе (граммы)")
                        api_response = {"result": "success", "chart_file": image_to_send}

                elif chart_type == "staff_history":
                    # Fetch all staff hookahs
                    records = await fetch_transactions(tx_type="staff")
                    daily_counts = defaultdict(int)
                    for r in records:
                        dt = r["date"].split("T")[0]
                        for item in r.get("items", []):
                            daily_counts[dt] += item.get("quantity", 1)
                    
                    if not daily_counts:
                        api_response = {"result": "error", "error": "Нет данных по стафф кальянам."}
                    else:
                        # Sort by date
                        sorted_dates = sorted(daily_counts.keys())
                        labels = [d.split("-")[2] + "." + d.split("-")[1] for d in sorted_dates[-30:]] # last 30 days
                        values = [daily_counts[d] for d in sorted_dates[-30:]]
                        
                        image_to_send = draw_bar_chart(labels, values, "Стафф кальяны (последние 30 дней)", "Дата", "Кол-во")
                        api_response = {"result": "success", "chart_file": image_to_send}
                else:
                    api_response = {"result": "error", "error": "Неизвестный тип графика."}
            except Exception as e:
                import logging
                logging.error(f"Error generating chart: {e}", exc_info=True)
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
        return {"text": final_response.text, "image": image_to_send}

    return {"text": response.text, "image": None}
