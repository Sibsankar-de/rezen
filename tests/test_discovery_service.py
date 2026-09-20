import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from models.device import Device
from protocol.packet import Packet, PacketType
from services.discovery_service import DiscoveryService


@pytest.mark.asyncio
async def test_discover_devices_with_device_payload():
    mock_broadcaster = MagicMock()
    mock_broadcaster.start = AsyncMock()
    mock_broadcaster.stop = AsyncMock()
    mock_dev_service = MagicMock()
    local_device = Device(id="local_id", name="Local", hostname="localhost", ip="127.0.0.1", port=45871, os="Linux")
    mock_dev_service.get_current_device.return_value = local_device

    service = DiscoveryService(broadcaster=mock_broadcaster, device_service=mock_dev_service)

    remote_device = Device(
        id="remote_device_1",
        name="Remote Device 1",
        hostname="remote-host",
        ip="192.168.1.100",
        port=45871,
        os="Linux",
    )

    def capture_subscribe(handler):
        remote_packet = Packet(
            type=PacketType.DISCOVER_RESPONSE,
            version="1",
            device_id="remote_device_1",
            payload=remote_device,
        )
        handler(remote_packet, ("192.168.1.100", 45871))

    mock_broadcaster.subscribe.side_effect = capture_subscribe

    devices = await service.discover_devices(timeout=0.01)

    assert len(devices) == 1
    assert isinstance(devices[0], Device)
    assert devices[0].id == "remote_device_1"
    assert devices[0].name == "Remote Device 1"
    assert devices[0].hostname == "remote-host"
    assert devices[0].ip == "192.168.1.100"
    assert devices[0].port == 45871
    assert devices[0].os == "Linux"

    mock_broadcaster.subscribe.assert_called_once()
    mock_broadcaster.unsubscribe.assert_called_once()


@pytest.mark.asyncio
async def test_discover_devices_ignores_self():
    mock_broadcaster = MagicMock()
    mock_broadcaster.start = AsyncMock()
    mock_broadcaster.stop = AsyncMock()
    mock_dev_service = MagicMock()
    local_device = Device(id="local_id", name="Local Host", hostname="localhost", ip="127.0.0.1", port=45871, os="Linux")
    mock_dev_service.get_current_device.return_value = local_device

    service = DiscoveryService(broadcaster=mock_broadcaster, device_service=mock_dev_service)

    def capture_subscribe(handler):
        self_packet = Packet(
            type=PacketType.DISCOVER_RESPONSE,
            version="1",
            device_id="local_id",
            payload=local_device,
        )
        handler(self_packet, ("127.0.0.1", 45871))

    mock_broadcaster.subscribe.side_effect = capture_subscribe

    devices = await service.discover_devices(timeout=0.01)
    assert len(devices) == 0


def test_device_converters():
    d_dict = {
        "id": "dev_123",
        "name": "My Device",
        "hostname": "my-host",
        "ip": "192.168.1.50",
        "port": 45871,
        "os": "Linux",
    }
    device = Device.from_payload(d_dict)
    assert isinstance(device, Device)
    assert device.id == "dev_123"
    assert device.name == "My Device"
    assert device.ip == "192.168.1.50"

    device_same = Device.from_payload(device)
    assert device_same is device
