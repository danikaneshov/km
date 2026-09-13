import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

ALLOWED_TELEGRAM_ID = int(os.getenv("ALLOWED_TELEGRAM_ID", 0)) if os.getenv("ALLOWED_TELEGRAM_ID") else None

LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID", "")
SECRET_PHRASE = os.getenv("SECRET_PHRASE", "огурец")
