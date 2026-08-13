import sqlite3
from typing import Optional

from settings import settings


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Return a SQLite database connection with row factory configured."""
    target_path = db_path or settings.db_path
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Initialize database tables if they do not exist."""
    with get_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.commit()
