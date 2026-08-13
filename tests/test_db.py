import sys
from pathlib import Path

import pytest

src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from db.repository import SettingsRepository
from settings import settings


def test_settings_repository_get_and_set(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_rezen.db")
    monkeypatch.setattr(settings, "db_path", db_file)
    repo = SettingsRepository()

    # Value does not exist initially
    assert repo.get_setting("device_id") is None

    # Set value
    repo.set_setting("device_id", "A1b2C3d4E5")
    assert repo.get_setting("device_id") == "A1b2C3d4E5"

    # Update value (ON CONFLICT)
    repo.set_setting("device_id", "Z9y8X7w6V5")
    assert repo.get_setting("device_id") == "Z9y8X7w6V5"
