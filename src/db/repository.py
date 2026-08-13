from typing import Optional

from db.connection import get_connection, init_db
from settings import settings


class SettingsRepository:
    """Repository for managing system settings stored in SQLite database."""

    def __init__(self):
        self.db_path = settings.db_path
        init_db(self.db_path)

    def get_setting(self, key: str) -> Optional[str]:
        """Retrieve a setting value by key from the database."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT value FROM system_settings WHERE key = ?", (key,)
            )
            row = cursor.fetchone()
            return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        """Store or update a key-value setting in the database."""
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO system_settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            conn.commit()
