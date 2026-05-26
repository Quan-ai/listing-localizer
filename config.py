import os
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
TEXT_MODEL = os.getenv("TEXT_MODEL", "deepseek-chat")
VISION_MODEL = os.getenv("VISION_MODEL", "deepseek-chat")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-in-production")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))

if not DEEPSEEK_API_KEY:
    raise RuntimeError("DEEPSEEK_API_KEY environment variable is required")
