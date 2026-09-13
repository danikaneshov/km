import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
ALLOWED_TELEGRAM_ID = os.getenv("ALLOWED_TELEGRAM_ID")

if ALLOWED_TELEGRAM_ID:
    ALLOWED_TELEGRAM_ID = int(ALLOWED_TELEGRAM_ID)
