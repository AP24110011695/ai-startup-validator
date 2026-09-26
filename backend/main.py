"""FastAPI app. Phase 1: health check + static frontend. API endpoints arrive in Phase 8."""
import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.config import LLM_MODEL, ROOT, USE_MOCK
from backend.logging_setup import setup_logging

setup_logging()
logger = logging.getLogger(__name__)
logger.info("startup: mock_mode=%s, llm_model=%s", USE_MOCK, LLM_MODEL)

app = FastAPI(title="AI Startup Validator")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "mock_mode": USE_MOCK}


app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
