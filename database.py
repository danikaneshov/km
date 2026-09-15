import motor.motor_asyncio
import config
from datetime import datetime
import certifi

# Initialize the motor client only if the URI is available
client = None
db = None
transactions_collection = None

if config.MONGODB_URI:
    client = motor.motor_asyncio.AsyncIOMotorClient(config.MONGODB_URI, tlsCAFile=certifi.where())
    db = client.hookah_jarvis
    transactions_collection = db.transactions
    admins_collection = db.admins
    surplus_collection = db.surplus
    usage_log_collection = db.usage_log

async def add_admin(user_id: int):
    if admins_collection is not None:
        await admins_collection.update_one({"user_id": user_id}, {"$set": {"user_id": user_id}}, upsert=True)

async def is_admin(user_id: int) -> bool:
    if config.ALLOWED_TELEGRAM_ID and user_id == config.ALLOWED_TELEGRAM_ID:
        return True
    if admins_collection is not None:
        admin = await admins_collection.find_one({"user_id": user_id})
        return admin is not None
    return False

async def set_base_surplus(tobacco_grams: int, coals_pieces: int):
    if surplus_collection is not None:
        await surplus_collection.update_one(
            {"_id": "main"}, 
            {"$set": {"tobacco_grams": tobacco_grams, "coals_pieces": coals_pieces}}, 
            upsert=True
        )

async def get_base_surplus() -> dict:
    if surplus_collection is not None:
        doc = await surplus_collection.find_one({"_id": "main"})
        if doc:
            return {"tobacco_grams": doc.get("tobacco_grams", 0), "coals_pieces": doc.get("coals_pieces", 0)}
    return {"tobacco_grams": 0, "coals_pieces": 0}

async def add_usage_log(date_str: str, usage_type: str, value1: int, value2: int):
    """
    usage_type: 'surplus' or 'staff'
    value1: tobacco grams (+ for surplus, - for staff)
    value2: coals pieces (+ for surplus, - for staff)
    """
    if usage_log_collection is not None:
        count = await usage_log_collection.count_documents({})
        doc = {
            "id": count + 1,
            "date": date_str,
            "type": usage_type,
            "value1": value1,
            "value2": value2
        }
        await usage_log_collection.insert_one(doc)

async def get_usage_log_totals() -> tuple[int, int]:
    if usage_log_collection is None:
        return 0, 0
    cursor = usage_log_collection.find({})
    tot_tobacco = 0
    tot_coals = 0
    async for doc in cursor:
        tot_tobacco += doc.get("value1", 0)
        tot_coals += doc.get("value2", 0)
    return tot_tobacco, tot_coals

async def save_transaction(date: str, items: list, raw_message: str, tx_type: str = "in"):
    """
    Saves a new transaction. tx_type: in, out, staff, replacement
    """
    if transactions_collection is None:
        raise Exception("Database is not configured.")

    try:
        dt = datetime.fromisoformat(date)
    except ValueError:
        dt = datetime.now()

    doc = {
        "date": dt,
        "type": tx_type,
        "items": items,
        "raw_message": raw_message,
        "created_at": datetime.now()
    }
    result = await transactions_collection.insert_one(doc)
    return str(result.inserted_id)

async def fetch_transactions(start_date: str = None, end_date: str = None, specific_day: int = None, tx_type: str = None):
    if transactions_collection is None:
        raise Exception("Database is not configured.")

    query = {}
    
    if start_date and end_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
            end_dt = datetime.fromisoformat(end_date)
            query["date"] = {"$gte": start_dt, "$lte": end_dt}
        except ValueError:
            pass
            
    if tx_type:
        query["type"] = tx_type

    cursor = transactions_collection.find(query)
    results = []
    async for doc in cursor:
        if specific_day is not None:
            if doc["date"].day != specific_day:
                continue
                
        doc['_id'] = str(doc['_id'])
        doc['date'] = doc['date'].isoformat()
        doc['created_at'] = doc['created_at'].isoformat()
        results.append(doc)
        
    return results

async def get_current_stock():
    if transactions_collection is None:
        raise Exception("Database is not configured.")
        
    cursor = transactions_collection.find({})
    stock = {}
    
    staff_hookahs_total = 0
    replacements_total = 0
    
    async for doc in cursor:
        t_type = doc.get("type", "in")
        
        if t_type == "staff":
            for item in doc.get("items", []):
                if "кальян" in str(item.get("category", "")).lower():
                    staff_hookahs_total += item.get("quantity", 1)
            continue
            
        if t_type == "replacement":
            for item in doc.get("items", []):
                if "кальян" in str(item.get("category", "")).lower():
                    replacements_total += item.get("quantity", 1)
            continue
            
        mult = 1 if t_type == "in" else -1
        
        for item in doc.get("items", []):
            cat = str(item.get("category", "неизвестно")).lower()
            brand = str(item.get("brand", "неизвестно")).lower()
            u_size = item.get("unit_size", 0)
            key = f"{cat}_{brand}_{u_size}"
            
            if key not in stock:
                stock[key] = {
                    "category": cat,
                    "brand": brand,
                    "quantity": 0,
                    "unit": item.get("unit", "шт"),
                    "unit_size": item.get("unit_size")
                }
                
            stock[key]["quantity"] += item.get("quantity", 0) * mult
            
    # Calculate live surplus
    base_surplus = await get_base_surplus()
    usage_tobacco, usage_coals = await get_usage_log_totals()
    
    net_staff_hookahs_historical = staff_hookahs_total - replacements_total
    
    live_surplus_tobacco = base_surplus["tobacco_grams"] - (net_staff_hookahs_historical * 23) + usage_tobacco
    live_surplus_coals = base_surplus["coals_pieces"] - (net_staff_hookahs_historical * 4) + usage_coals

    final_stock = [v for v in stock.values() if v["quantity"] != 0]
    
    exact_warehouse_tobacco_grams = 0
    exact_warehouse_coals_pieces = 0
    
    for item in final_stock:
        cat = item["category"]
        size = item["unit_size"] or 1
        qty = item["quantity"]
        if "табак" in cat:
            exact_warehouse_tobacco_grams += qty * size
        elif "угл" in cat:
            exact_warehouse_coals_pieces += qty * size

    return {
        "stock": final_stock,
        "staff_hookahs_total": staff_hookahs_total,
        "replacements_total": replacements_total,
        "surplus_tobacco_grams": live_surplus_tobacco,
        "surplus_coals_pieces": live_surplus_coals,
        "exact_totals_calculated_by_system": {
            "warehouse_tobacco_grams": exact_warehouse_tobacco_grams,
            "warehouse_coals_pieces": exact_warehouse_coals_pieces
        }
    }
