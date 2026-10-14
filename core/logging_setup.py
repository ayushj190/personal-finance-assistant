import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys

from core.config import DATA_DIR

LOGS_DIR = DATA_DIR / "logs"
LOG_FILE = LOGS_DIR / "app.log"
_CONFIGURED = False


def configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    level_name = os.environ.get("PFA_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler: 1 MB max size, 3 backups
    file_handler = RotatingFileHandler(
        str(LOG_FILE),
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Console (stderr) handler
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    _CONFIGURED = True
