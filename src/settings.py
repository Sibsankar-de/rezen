from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    VERSION: str = "0.1.0"
    version: str = "0.1.0"

    # Environment & Logging
    APP_ENV: str = "production"
    APP_DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    LOG_TO_CONSOLE: bool = False
    LOG_FILE: str = "logs/rezen.log"
    LOG_MAX_BYTES: int = 10 * 1024 * 1024
    LOG_BACKUP_COUNT: int = 5

    # Database
    db_path: str = "rezen.db"

    # Screen Capture & Streaming
    STREAM_QUEUE_MAX_SIZE: int = 10000
    STREAM_CHUNK_SIZE: int = 16 * 1024

    SCREEN_RENDER_WINDOW_NAME: str = "Rezen - Remote screen"

    # Capture backend: "auto" prefers the Wayland portal when available.
    SCREEN_CAPTURE_BACKEND: str = "auto"
    SCREEN_CAPTURE_MAX_WIDTH: int = 1280
    SCREEN_CAPTURE_MAX_HEIGHT: int = 720

    # Encoder tuning. ultrafast disables deblocking and CABAC, which is very
    # visible on text, so a slower preset is used by default.
    SCREEN_STREAM_BITRATE: int = 8_000_000
    SCREEN_STREAM_PRESET: str = "veryfast"

    INPUT_STREAM_QUEUE_MAX_SIZE: int = 10000
    INPUT_RECEIVE_QUEUE_MAX_SIZE: int = 10000

    model_config = SettingsConfigDict(
        env_file=(".env", str(Path(__file__).resolve().parent.parent / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
