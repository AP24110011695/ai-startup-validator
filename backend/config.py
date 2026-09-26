"""Settings loaded once from .env / environment; the single import point for config."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

USE_MOCK: bool = os.getenv("USE_MOCK", "true").lower() == "true"
LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-2.5-flash")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

API_KEYS: dict[str, str] = {
    "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY", ""),
    "TAVILY_API_KEY": os.getenv("TAVILY_API_KEY", ""),
    "SERPAPI_API_KEY": os.getenv("SERPAPI_API_KEY", ""),
}


def set_api_key(name: str, value: str) -> None:
    """Hot-swap an API key at runtime (wired into the HTTP API in Phase 8)."""
    raise NotImplementedError("set_api_key is wired into the API in Phase 8")
