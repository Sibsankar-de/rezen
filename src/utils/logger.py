import logging
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.logging import RichHandler

from settings import settings

LOG_FORMAT = "%(asctime)s | RUN=%(run_id)s | %(name)s | %(funcName)s:%(lineno)d - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

DEBUG_ENABLED = settings.APP_DEBUG
LOG_LEVEL = logging.DEBUG if DEBUG_ENABLED else getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

# Unique ID for this application run
RUN_ID = uuid.uuid4().hex[:8]


class RunIdFilter(logging.Filter):
    """Add the current application run ID to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = RUN_ID
        return True


def get_log_file_path() -> Path:
    """Resolve the log file path relative to project root if relative."""
    project_root = Path(__file__).resolve().parent.parent.parent
    raw_path = Path(settings.LOG_FILE)
    if not raw_path.is_absolute():
        log_path = (project_root / raw_path).resolve()
    else:
        log_path = raw_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return log_path


def setup_logging(force_console: bool | None = None) -> None:
    """Configure application-wide logging.

    In production, logs are directed cleanly to the rotating log file to prevent
    terminal clutter. Console logging can be enabled via settings.LOG_TO_CONSOLE
    or in development environment.
    """
    root_logger = logging.getLogger()

    # Prevent duplicate configuration
    if root_logger.handlers:
        return

    # Determine effective log level
    if settings.APP_DEBUG:
        effective_level = logging.DEBUG
    else:
        effective_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    root_logger.setLevel(effective_level)

    formatter = logging.Formatter(
        LOG_FORMAT,
        datefmt=DATE_FORMAT,
    )

    # 1. Rotating File Handler (always active, persists all logs safely)
    log_file = get_log_file_path()
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=settings.LOG_MAX_BYTES,
        backupCount=settings.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(effective_level)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(RunIdFilter())
    root_logger.addHandler(file_handler)

    # 2. Console Handler (only enabled when explicitly requested or in dev mode)
    is_dev = settings.APP_ENV.lower() in ("development", "dev")
    should_log_console = (
        force_console
        if force_console is not None
        else (settings.LOG_TO_CONSOLE or (is_dev and settings.APP_DEBUG))
    )

    if should_log_console:
        console_handler = RichHandler(
            rich_tracebacks=True,
            markup=True,
            show_path=False,
        )
        console_handler.setLevel(effective_level)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(RunIdFilter())
        root_logger.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)
