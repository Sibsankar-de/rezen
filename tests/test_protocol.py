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


def test_tcp_serializer_roundtrip_bytes():
    from protocol.serializer import TCPSerializer

    pkt = Packet(
        type=PacketType.HELLO,
        version="1",
        device_id="dev123",
        payload={"foo": "bar"},
    )
    raw = TCPSerializer.serialize(pkt)
    assert isinstance(raw, bytes)
    assert len(raw) > TCPSerializer.HEADER_SIZE

    deserialized = asyncio.run(TCPSerializer.deserialize(raw))
    assert deserialized.type == PacketType.HELLO
    assert deserialized.device_id == "dev123"
    assert deserialized.payload == {"foo": "bar"}


@pytest.mark.asyncio
async def test_tcp_serializer_stream_reader():
    from protocol.serializer import TCPSerializer

    pkt = Packet(
        type=PacketType.HELLO_ACK,
        version="1",
        device_id="dev456",
        payload={"ok": True},
    )
    raw = TCPSerializer.serialize(pkt)

    reader = asyncio.StreamReader()
    reader.feed_data(raw)
    reader.feed_eof()

    deserialized = await TCPSerializer.deserialize(reader)
    assert deserialized.type == PacketType.HELLO_ACK
    assert deserialized.device_id == "dev456"
    assert deserialized.payload == {"ok": True}


@pytest.mark.asyncio
async def test_connection_manager_connect_and_exchange():
    from models.device import Device
    from models.connection import ConnectionState
    from protocol.connection_manager import ConnectionManager

    dev1 = Device(id="dev1", name="Device One", hostname="h1", ip="127.0.0.1", port=45895, os="Linux")
    dev2 = Device(id="dev2", name="Device Two", hostname="h2", ip="127.0.0.1", port=45896, os="Linux")

    cm1 = ConnectionManager(current_device=dev1, port=45895)
    cm2 = ConnectionManager(current_device=dev2, port=45896)

    server_received = []

    async def server_handler(conn, pkt):
        server_received.append((conn, pkt))

    await cm2.subscribe(server_handler)

    await cm1.start()
    await cm2.start()

    try:
        conn = await cm1.connect(dev2)
        assert conn.state == ConnectionState.CONNECTED

        await asyncio.sleep(0.1)

        # Send ping from dev1 to dev2
        ping = Packet(type=PacketType.PING, version="1", device_id=dev1.id, payload={"hello": "world"})
        await cm1.send(conn.id, ping)
        await asyncio.sleep(0.1)

        assert any(pkt.type == PacketType.PING for _, pkt in server_received)

        await cm1.disconnect(conn.id)
    finally:
        await cm1.stop()
        await cm2.stop()

