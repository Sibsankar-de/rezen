import logging
import os

from rich.logging import RichHandler

# Log message format
LOG_FORMAT = "| %(name)s | %(funcName)s:%(lineno)d - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

DEBUG_ENABLED = os.getenv("APP_DEBUG", "false").lower() == "true"


def get_logger(name: str) -> logging.Logger:
    """
    Create and return a logger instance with Rich formatting.
    """
    level = logging.DEBUG if DEBUG_ENABLED else logging.INFO

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid adding duplicate handlers
    if not logger.handlers:
        console_handler = RichHandler(
            rich_tracebacks=True,
            markup=True,
            show_path=False,
        )

        formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger
