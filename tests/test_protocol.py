import sys
import asyncio
from pathlib import Path

import pytest

src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from protocol.broadcaster import Broadcaster
from protocol.packet import Packet, PacketType
from protocol.serializer import PacketSerializer


def test_packet_serializer_roundtrip_bytes():
    pkt = Packet(
        type=PacketType.DISCOVER,
        version="1",
        device_id="dev123",
        payload={"key": "value"},
    )
    raw_bytes = PacketSerializer.dumps(pkt)
    assert isinstance(raw_bytes, bytes)

    loaded_from_bytes = PacketSerializer.loads(raw_bytes)
    assert loaded_from_bytes.type == PacketType.DISCOVER
    assert loaded_from_bytes.device_id == "dev123"
    assert loaded_from_bytes.payload == {"key": "value"}


def test_broadcaster_deserialize_does_not_raise():
    pkt = Packet(
        type=PacketType.DISCOVER,
        version="1",
        device_id="dev_test",
        payload={},
    )
    data = PacketSerializer.dumps(pkt)
    result = Broadcaster._deserialize(data)
    assert result.device_id == "dev_test"
    assert result.type == PacketType.DISCOVER


@pytest.mark.asyncio
async def test_broadcaster_real_udp_send_and_receive():
    received = []

    def handler(packet, address):
        received.append((packet, address))

    broadcaster = Broadcaster()
    broadcaster.subscribe(handler)
    await broadcaster.start()

    try:
        pkt = Packet(
            type=PacketType.PING,
            version="1",
            device_id="ping_device",
            payload={},
        )
        broadcaster.send(pkt, ("127.0.0.1", broadcaster._port))
        await asyncio.sleep(0.3)

        assert len(received) >= 1
        assert received[0][0].device_id == "ping_device"
        assert received[0][0].type == PacketType.PING
    finally:
        await broadcaster.stop()
