from datetime import datetime, timedelta

import certifi
import motor.motor_asyncio

from config import MONGODB_URI, DB_NAME, SURPLUS_TOBACCO_GRAMS, SURPLUS_COALS_COUNT, STAFF_COALS_COUNT

# ---------------------------------------------------------------------------
# Подключение
# ---------------------------------------------------------------------------
_client = motor.motor_asyncio.AsyncIOMotorClient(
    MONGODB_URI,
    tlsCAFile=certifi.where(),
)
db = _client[DB_NAME]

admins_col = db["admins"]
warehouse_col = db["warehouse"]
balance_col = db["balance_log"]


# ---------------------------------------------------------------------------
# Admins
# ---------------------------------------------------------------------------
async def is_admin(telegram_id: int) -> bool:
    """Проверяет, авторизован ли пользователь."""
    return await admins_col.find_one({"telegram_id": telegram_id}) is not None


async def add_admin(telegram_id: int) -> None:
    """Добавляет пользователя в список авторизованных."""
    if not await is_admin(telegram_id):
        await admins_col.insert_one({
            "telegram_id": telegram_id,
            "added_at": datetime.utcnow(),
        })


async def ensure_owner(owner_id: int) -> None:
    """Гарантирует, что основной аккаунт есть в admins."""
    await add_admin(owner_id)


# ---------------------------------------------------------------------------
# Склад (приходы)
# ---------------------------------------------------------------------------
async def add_warehouse_entry(
    items: list[dict], notes: str = "", date: datetime | None = None
) -> dict:
    """
    Записывает приход на склад.
    items: [{"brand": "BlackBurn", "flavor": "Something", "weight_g": 250}, ...]
    """
    doc = {
        "date": date or datetime.utcnow(),
        "items": items,
        "notes": notes,
    }
    result = await warehouse_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def get_warehouse_history(days: int = 30) -> list[dict]:
    """Возвращает историю приходов за последние N дней."""
    since = datetime.utcnow() - timedelta(days=days)
    cursor = warehouse_col.find({"date": {"$gte": since}}).sort("date", -1)
    return await cursor.to_list(length=200)


# ---------------------------------------------------------------------------
# Баланс: излишки и стафф
# ---------------------------------------------------------------------------
async def add_surplus(bowls: int, user_id: int, date: datetime | None = None) -> dict:
    """Зачисляет излишек на баланс (нескуренные чаши)."""
    tobacco = bowls * SURPLUS_TOBACCO_GRAMS
    coals = bowls * SURPLUS_COALS_COUNT
    doc = {
        "date": date or datetime.utcnow(),
        "type": "surplus",
        "bowls": bowls,
        "tobacco_g": tobacco,
        "coals": coals,
        "user_id": user_id,
    }
    await balance_col.insert_one(doc)
    return doc


async def add_staff(tobacco_g: float, user_id: int, date: datetime | None = None) -> dict:
    """Списывает стафф-кальян с баланса (граммы вручную, угли фикс 4)."""
    doc = {
        "date": date or datetime.utcnow(),
        "type": "staff",
        "bowls": 1,
        "tobacco_g": tobacco_g,
        "coals": STAFF_COALS_COUNT,
        "user_id": user_id,
    }
    await balance_col.insert_one(doc)
    return doc


async def get_balance() -> dict:
    """
    Считает текущий баланс излишков.
    Возвращает: {"bowls": N, "tobacco_g": N, "coals": N}
    """
    pipeline = [
        {
            "$group": {
                "_id": "$type",
                "total_bowls": {"$sum": "$bowls"},
                "total_tobacco": {"$sum": "$tobacco_g"},
                "total_coals": {"$sum": "$coals"},
            }
        }
    ]
    results = await balance_col.aggregate(pipeline).to_list(length=10)

    surplus = {"bowls": 0, "tobacco_g": 0, "coals": 0}
    staff = {"bowls": 0, "tobacco_g": 0, "coals": 0}

    for r in results:
        target = surplus if r["_id"] == "surplus" else staff
        target["bowls"] = r["total_bowls"]
        target["tobacco_g"] = r["total_tobacco"]
        target["coals"] = r["total_coals"]

    return {
        "bowls": surplus["bowls"] - staff["bowls"],
        "tobacco_g": surplus["tobacco_g"] - staff["tobacco_g"],
        "coals": surplus["coals"] - staff["coals"],
    }


async def get_history(days: int = 7) -> list[dict]:
    """
    Возвращает историю излишков/стаффов за последние N дней,
    сгруппированную по дням.
    """
    since = datetime.utcnow() - timedelta(days=days)
    pipeline = [
        {"$match": {"date": {"$gte": since}}},
        {
            "$group": {
                "_id": {
                    "date": {
                        "$dateToString": {"format": "%Y-%m-%d", "date": "$date"}
                    },
                    "type": "$type",
                },
                "total_bowls": {"$sum": "$bowls"},
                "total_tobacco": {"$sum": "$tobacco_g"},
                "total_coals": {"$sum": "$coals"},
            }
        },
        {"$sort": {"_id.date": 1}},
    ]
    return await balance_col.aggregate(pipeline).to_list(length=200)
