import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE)

APP_NAME = "Natural Language BI Assistant"
APP_VERSION = "1.0.0"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6")
ENABLE_LLM_FALLBACK = os.getenv("ENABLE_LLM_FALLBACK", "false").lower() in {"1", "true", "yes"}
USE_LLM_ANSWER = os.getenv("USE_LLM_ANSWER", "false").lower() in {"1", "true", "yes"}
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{(PROJECT_DIR / 'data' / 'bi.db').as_posix()}"
MAX_RESULT_ROWS = int(os.getenv("MAX_RESULT_ROWS", "200"))
MAX_RECOVERY_RETRIES = int(os.getenv("MAX_RECOVERY_RETRIES", "1"))

CORS_ORIGINS = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174").split(",") if origin.strip()]
