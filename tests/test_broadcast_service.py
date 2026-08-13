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


def test_broadcast_service_start_stop():
    mock_broadcaster = MagicMock()
    mock_dev_service = MagicMock()
    device = Device(id="local_dev", name="Local Device", hostname="host", ip="127.0.0.1", port=45871, os="Linux")
    mock_dev_service.get_current_device.return_value = device

    service = BroadcastService(broadcaster=mock_broadcaster, device_service=mock_dev_service)

    service.start_private_broadcast()
    mock_broadcaster.start.assert_called_once()
    mock_broadcaster.subscribe.assert_called_once()

    service.stop_private_broadcast()
    mock_broadcaster.stop.assert_called_once()
    mock_broadcaster.unsubscribe.assert_called_once()


def test_broadcast_service_responds_to_discover():
    mock_broadcaster = MagicMock()
    mock_dev_service = MagicMock()
    device = Device(id="local_dev", name="Local Device", hostname="host", ip="127.0.0.1", port=45871, os="Linux")
    mock_dev_service.get_current_device.return_value = device

    service = BroadcastService(broadcaster=mock_broadcaster, device_service=mock_dev_service)

    subscribed_handler = None

    def capture_subscribe(handler):
        nonlocal subscribed_handler
        subscribed_handler = handler

    mock_broadcaster.subscribe.side_effect = capture_subscribe
    service.start_private_broadcast()

    discover_packet = Packet(
        type=PacketType.DISCOVER,
        version="1",
        device_id="remote_dev",
        payload={"name": "Remote", "port": 45871},
    )

    subscribed_handler(discover_packet, ("192.168.1.50", 45871))

    mock_broadcaster.send.assert_called_once()
    sent_packet, target_addr = mock_broadcaster.send.call_args[0]
    assert sent_packet.type == PacketType.DISCOVER_RESPONSE
    assert sent_packet.device_id == "local_dev"
    assert sent_packet.payload == device
    assert target_addr == ("192.168.1.50", 45871)


def test_broadcast_service_broadcast_custom_packet():
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

    service.broadcast(custom_packet)
    mock_broadcaster.broadcast.assert_called_once_with(custom_packet)


def test_broadcast_service_broadcast_default_packet():
    mock_broadcaster = MagicMock()
    mock_dev_service = MagicMock()
    device = Device(id="test_dev", name="Test Device", hostname="host", ip="127.0.0.1", port=45871, os="Linux")
    mock_dev_service.get_current_device.return_value = device

    service = BroadcastService(broadcaster=mock_broadcaster, device_service=mock_dev_service)

    service.broadcast()
    mock_broadcaster.broadcast.assert_called_once()
    sent_packet = mock_broadcaster.broadcast.call_args[0][0]
    assert sent_packet.type == PacketType.DISCOVER
    assert sent_packet.device_id == "test_dev"
    assert sent_packet.payload == device
