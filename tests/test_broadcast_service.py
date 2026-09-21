import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from models.device import Device
from protocol.packet import Packet, PacketType
from services.broadcast_service import BroadcastService


@pytest.mark.asyncio
async def test_broadcast_service_start_stop():
    mock_dev_service = MagicMock()
    device = Device(id="local_dev", name="Local Device", hostname="host", ip="127.0.0.1", port=45871, os="Linux")
    mock_dev_service.get_current_device.return_value = device

    service = BroadcastService(device_service=mock_dev_service)
    await service.start_private_broadcast()

    assert service._broadcaster is not None
    assert service._broadcast_task is not None

    await service.stop_private_broadcast()

    assert service._broadcaster is None
    assert service._broadcast_task is None


@pytest.mark.asyncio
async def test_broadcast_service_broadcast_custom_packet():
    mock_broadcaster = MagicMock()
    mock_dev_service = MagicMock()
    device = Device(id="test_dev", name="Test Device", hostname="host", ip="127.0.0.1", port=45871, os="Linux")
    mock_dev_service.get_current_device.return_value = device

    service = BroadcastService(broadcaster=mock_broadcaster, device_service=mock_dev_service)

    custom_packet = Packet(
        type=PacketType.PING,
        version="1",
        device_id="test_dev",
        payload={},
    )

    await service.broadcast(custom_packet)
    mock_broadcaster.broadcast.assert_called_once_with(custom_packet)


@pytest.mark.asyncio
async def test_broadcast_service_broadcast_default_packet():
    mock_broadcaster = MagicMock()
    mock_dev_service = MagicMock()
    device = Device(id="test_dev", name="Test Device", hostname="host", ip="127.0.0.1", port=45871, os="Linux")
    mock_dev_service.get_current_device.return_value = device

    service = BroadcastService(broadcaster=mock_broadcaster, device_service=mock_dev_service)

    await service.broadcast()
    mock_broadcaster.broadcast.assert_called_once()
    sent_packet = mock_broadcaster.broadcast.call_args[0][0]
    assert sent_packet.type == PacketType.DISCOVER
    assert sent_packet.device_id == "test_dev"
    assert sent_packet.payload == device
