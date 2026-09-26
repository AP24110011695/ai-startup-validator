"""Settings loaded once from .env / environment; the single import point for config."""
import os
from contextvars import ContextVar
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

USE_MOCK: bool = os.getenv("USE_MOCK", "true").lower() == "true"
LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-3.8-flash")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
FAKE_QUOTA_ERROR: bool = os.getenv("FAKE_QUOTA_ERROR", "") == "1"

API_KEYS: dict[str, str] = {
    "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY", ""),
    "TAVILY_API_KEY": os.getenv("TAVILY_API_KEY", ""),
    "SERPAPI_API_KEY": os.getenv("SERPAPI_API_KEY", ""),
}

# Per-run mock override, set by the API layer inside each run's thread (None =
# fall back to the USE_MOCK env default). Contextvar so concurrent runs with
# different toggle states never cross wires.
mock_override: ContextVar[bool | None] = ContextVar("mock_override", default=None)


def use_mock() -> bool:
    """Effective mock mode for the current run: the per-request toggle wins over
    the server-level USE_MOCK env default."""
    override = mock_override.get()
    return USE_MOCK if override is None else override


def set_api_key(name: str, value: str) -> None:
    """Hot-swap an API key at runtime (used by POST /api/key): updates the in-memory
    dict that every module reads from, and persists to .env so restarts keep it."""
    if name not in API_KEYS:
        raise ValueError(f"unknown API key: {name}")
    API_KEYS[name] = value
    _persist_to_env(name, value)


def _persist_to_env(name: str, value: str) -> None:
    env_path = ROOT / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    for i, line in enumerate(lines):
        if line.startswith(f"{name}="):
            lines[i] = f"{name}={value}"
            break
    else:
        lines.append(f"{name}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
