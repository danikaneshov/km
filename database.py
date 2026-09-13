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

async def save_transaction(date: str, items: list, raw_message: str, tx_type: str = "in"):
    """
    Saves a new transaction (delivery 'in' or expense 'out').
    date: ISO string like '2023-10-25T00:00:00'
    items: list of dictionaries with extracted information
    tx_type: "in" for deliveries, "out" for expenses
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
    """
    Fetches transactions based on date range and optional type.
    """
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
    """
    Calculates the current stock by summing up all 'in' and subtracting 'out' transactions.
    """
    if transactions_collection is None:
        raise Exception("Database is not configured.")
        
    cursor = transactions_collection.find({})
    stock = {}
    
    staff_hookahs_total = 0
    
    async for doc in cursor:
        t_type = doc.get("type", "in")
        
        if t_type == "staff":
            for item in doc.get("items", []):
                if "кальян" in str(item.get("category", "")).lower():
                    staff_hookahs_total += item.get("quantity", 1)
            continue
            
        mult = 1 if t_type == "in" else -1
        
        for item in doc.get("items", []):
            cat = str(item.get("category", "неизвестно")).lower()
            brand = str(item.get("brand", "неизвестно")).lower()
            key = f"{cat}_{brand}"
            
            if key not in stock:
                stock[key] = {
                    "category": cat,
                    "brand": brand,
                    "quantity": 0,
                    "unit": item.get("unit", "шт"),
                    "unit_size": item.get("unit_size")
                }
                
            stock[key]["quantity"] += item.get("quantity", 0) * mult
            
    # Return dictionary with stock and staff stats
    return {
        "stock": [v for v in stock.values() if v["quantity"] != 0],
        "staff_hookahs_total": staff_hookahs_total
    }
