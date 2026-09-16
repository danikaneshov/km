import os
from dotenv import load_dotenv

load_dotenv()

# --- Telegram ---
TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
ALLOWED_TELEGRAM_ID: int = int(os.getenv("ALLOWED_TELEGRAM_ID", "0"))
LOG_CHANNEL_ID: int = int(os.getenv("LOG_CHANNEL_ID", "0"))
SECRET_PHRASE: str = os.getenv("SECRET_PHRASE", "")

# --- MongoDB ---
MONGODB_URI: str = os.getenv("MONGODB_URI", "")
DB_NAME: str = "hookah_master"

# --- Gemini ---
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = "gemini-flash-lite-latest"

# --- Шаблон чаши ---
SURPLUS_TOBACCO_GRAMS: int = 23
SURPLUS_COALS_COUNT: int = 5
STAFF_COALS_COUNT: int = 4

# --- Справочник брендов ---
BRAND_ALIASES: dict[str, str] = {
    "бб": "BlackBurn",
    "блэкберн": "BlackBurn",
    "blackburn": "BlackBurn",
    "дс": "DarkSide",
    "дарксайд": "DarkSide",
    "darkside": "DarkSide",
    "мастхэв": "MustHave",
    "масхев": "MustHave",
    "musthave": "MustHave",
    "краун": "Crown",
    "crown": "Crown",
    "коколоко": "Cocoloco",
    "cocoloco": "Cocoloco",
    "себеро": "Sebero",
    "sebero": "Sebero",
    "вкус": "Vkuss",
    "vkuss": "Vkuss",
    "джем": "Jam",
    "jam": "Jam",
    "хелл": "Hell",
    "hell": "Hell",
    "овердоз": "Overdose",
    "overdose": "Overdose",
    "сарма": "Sarma",
    "sarma": "Sarma",
}

KNOWN_BRANDS: list[str] = [
    "BlackBurn", "MustHave", "DarkSide", "Crown", "Cocoloco",
    "Sebero", "Vkuss", "Jam", "Hell", "Overdose", "Sarma",
]
