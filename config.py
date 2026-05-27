import os
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
TEXT_MODEL = os.getenv("TEXT_MODEL", "deepseek-chat")
VISION_MODEL = os.getenv("VISION_MODEL", "deepseek-chat")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-in-production")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))

DATABASE_PATH = os.environ.get("DATABASE_PATH", "data/localizer.db")
DAILY_FREE_LIMIT = int(os.environ.get("DAILY_FREE_LIMIT", "3"))
LOCAL_UTC_OFFSET = int(os.environ.get("LOCAL_UTC_OFFSET", "8"))
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

TURSO_URL = os.environ.get("TURSO_URL", "")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "")

if not DEEPSEEK_API_KEY:
    print("WARNING: DEEPSEEK_API_KEY is not set. LLM features will not work.")
