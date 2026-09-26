"""Logging setup: logs/app.log + console. Called once from backend.main."""
import logging

from backend.config import LOG_LEVEL, ROOT

LOG_FILE = ROOT / "logs" / "app.log"


def setup_logging() -> None:
    (ROOT / "logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
