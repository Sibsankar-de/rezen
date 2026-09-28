import logging
import os
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.logging import RichHandler

LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / "rezen.log"

LOG_FORMAT = "%(asctime)s | RUN=%(run_id)s | %(name)s | %(funcName)s:%(lineno)d - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

DEBUG_ENABLED = os.getenv("APP_DEBUG", "false").lower() == "true"

LOG_LEVEL = logging.DEBUG if DEBUG_ENABLED else logging.INFO

# Unique ID for this application run
RUN_ID = uuid.uuid4().hex[:8]


class RunIdFilter(logging.Filter):
    """Add the current application run ID to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = RUN_ID
        return True


def setup_logging() -> None:
    """Configure application-wide logging."""

    root_logger = logging.getLogger()

    # Prevent duplicate configuration
    if root_logger.handlers:
        return

    root_logger.setLevel(LOG_LEVEL)

    formatter = logging.Formatter(
        LOG_FORMAT,
        datefmt=DATE_FORMAT,
    )

    console_handler = RichHandler(
        rich_tracebacks=True,
        markup=True,
        show_path=False,
    )

    console_handler.setLevel(LOG_LEVEL)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(RunIdFilter())

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )

    file_handler.setLevel(LOG_LEVEL)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(RunIdFilter())

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""

    return logging.getLogger(name)
