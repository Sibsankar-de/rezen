from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    db_path: str = "rezen.db"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

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



settings = Settings()
