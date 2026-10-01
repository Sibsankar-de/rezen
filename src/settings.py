from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    db_path: str = "rezen.db"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    STREAM_QUEUE_MAX_SIZE: int = 10000
    STREAM_CHUNK_SIZE: int = 16 * 1024


settings = Settings()
