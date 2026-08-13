import sys
from pathlib import Path

import pytest

src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from models.device import Device
from services.device_service import DeviceService, get_local_ip
from settings import settings


def test_get_current_device_returns_device_instance(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_rezen_device.db")
    monkeypatch.setattr(settings, "db_path", db_file)
    service = DeviceService()
    device = service.get_current_device()

    assert isinstance(device, Device)
    assert len(device.id) == 10
    assert device.id.isalnum()
    assert device.port == 45871
    assert device.os != ""
    assert device.hostname != ""
    assert device.ip != ""


def test_get_local_ip():
    ip = get_local_ip()
    assert isinstance(ip, str)
    assert len(ip.split(".")) == 4


def test_device_service_generates_and_persists_10_char_alphanumeric_id(tmp_path, monkeypatch):
    db_file = str(tmp_path / "device_test.db")
    monkeypatch.setattr(settings, "db_path", db_file)

    # First instantiation: generates a 10-digit alphanumeric ID and saves to DB
    service1 = DeviceService()
    dev1 = service1.get_current_device()

    assert len(dev1.id) == 10
    assert dev1.id.isalnum()

    # Second instantiation: reuses the existing ID from DB
    service2 = DeviceService()
    dev2 = service2.get_current_device()

    assert dev2.id == dev1.id
