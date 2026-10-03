import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from container import Container
from models.connection import Connection, ConnectionState
from models.device import Device
from models.stream_chunk import ChunkType, FlagType, StreamChunk
from protocol.packet import Packet, PacketType
from services.screen_cast_service import ScreenCastService


@pytest.fixture
def mock_device():
    return Device(
        id="dev_1",
        name="Device One",
        hostname="h1",
        ip="127.0.0.1",
        port=45871,
        os="Linux",
    )


@pytest.fixture
def screen_cast_setup(mock_device):
    cm = MagicMock()
    cm.subscribe = AsyncMock()
    cm.unsubscribe = AsyncMock()

    mock_conn = MagicMock(spec=Connection)
    mock_conn.id = "conn_1"
    mock_conn.device_id = "remote_dev"
    mock_conn.state = ConnectionState.CONNECTED

    cs = MagicMock()
    cs.send_to_latest = AsyncMock()
    cs.latest_connection = mock_conn

    ds = MagicMock()
    ds.get_current_device.return_value = mock_device

    streamer = MagicMock()
    streamer.start = AsyncMock()
    streamer.stop = AsyncMock()

    receiver = MagicMock()
    receiver.start = AsyncMock()
    receiver.stop = AsyncMock()
    receiver.handle_chunk = AsyncMock()

    service = ScreenCastService(
        connection_manager=cm,
        connection_service=cs,
        device_service=ds,
        streamer=streamer,
        receiver=receiver,
    )

    return service, cm, cs, ds, streamer, receiver


@pytest.mark.asyncio
async def test_start_and_stop_streaming(screen_cast_setup):
    service, _, _, _, streamer, _ = screen_cast_setup

    await service.start_streaming()
    streamer.start.assert_awaited_once()

    await service.stop_streaming()
    streamer.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_and_stop_receiving(screen_cast_setup):
    service, cm, _, _, _, receiver = screen_cast_setup

    await service.start_receiving()
    receiver.start.assert_awaited_once()
    cm.subscribe.assert_awaited_once_with(service._handle_stream_packet)

    await service.stop_receiving()
    cm.unsubscribe.assert_awaited_once_with(service._handle_stream_packet)
    receiver.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_chunk(screen_cast_setup, mock_device):
    service, _, cs, _, _streamer, _ = screen_cast_setup

    chunk = StreamChunk(
        frame_id="frame_0",
        chunk_id="chunk_0",
        type=ChunkType.VIDEO,
        flag=FlagType.START_CHUNK,
        size=10,
        total_chunks=1,
        data=b"0123456789",
    )

    await service._send_chunk(chunk)
    cs.send_to_latest.assert_awaited_once()

    sent_packet: Packet = cs.send_to_latest.call_args[0][0]
    assert sent_packet.type == PacketType.SCREEN_FRAME_CHUNK
    assert sent_packet.version == "1.0"
    assert sent_packet.device_id == mock_device.id
    assert sent_packet.payload == chunk


@pytest.mark.asyncio
async def test_handle_stream_packet_valid_chunk(screen_cast_setup):
    service, _, cs, _, _, receiver = screen_cast_setup

    conn = cs.latest_connection
    chunk = StreamChunk(
        frame_id="frame_0",
        chunk_id="chunk_0",
        type=ChunkType.VIDEO,
        flag=FlagType.START_CHUNK,
        size=4,
        total_chunks=1,
        data=b"data",
    )
    packet = Packet(
        type=PacketType.SCREEN_FRAME_CHUNK,
        version="1.0",
        device_id="remote_dev",
        payload=chunk,
    )

    await service._handle_stream_packet(conn, packet)
    receiver.handle_chunk.assert_awaited_once_with(chunk)


@pytest.mark.asyncio
async def test_handle_stream_packet_dict_payload(screen_cast_setup):
    service, _, cs, _, _, receiver = screen_cast_setup

    conn = cs.latest_connection
    chunk_dict = {
        "frame_id": "frame_1",
        "chunk_id": "chunk_0",
        "type": ChunkType.VIDEO,
        "flag": FlagType.START_CHUNK,
        "size": 4,
        "total_chunks": 1,
        "data": b"test",
    }
    packet = Packet(
        type=PacketType.SCREEN_FRAME_CHUNK,
        version="1.0",
        device_id="remote_dev",
        payload=chunk_dict,
    )

    await service._handle_stream_packet(conn, packet)
    receiver.handle_chunk.assert_awaited_once()
    received_chunk = receiver.handle_chunk.call_args[0][0]
    assert isinstance(received_chunk, StreamChunk)
    assert received_chunk.frame_id == "frame_1"


@pytest.mark.asyncio
async def test_handle_stream_packet_mismatched_connection_ignored(screen_cast_setup):
    service, _, _cs, _, _, receiver = screen_cast_setup

    other_conn = MagicMock(spec=Connection)
    other_conn.id = "conn_other"

    packet = Packet(
        type=PacketType.SCREEN_FRAME_CHUNK,
        version="1.0",
        device_id="other_dev",
        payload={"dummy": "payload"},
    )

    await service._handle_stream_packet(other_conn, packet)
    receiver.handle_chunk.assert_not_called()


@pytest.mark.asyncio
async def test_container_screen_cast_service_property():
    container = Container()

    bc = MagicMock()
    bc.stop = AsyncMock()
    cm = MagicMock()
    cm.stop = AsyncMock()
    ds = MagicMock()

    container._broadcaster = bc
    container._connection_manager = cm
    container._device_service = ds

    svc1 = container.screen_cast_service
    svc2 = container.screen_cast_service
    assert svc1 is svc2
    assert isinstance(svc1, ScreenCastService)

    # Container stop shuts down screen_cast_service
    svc1.stop_streaming = AsyncMock()
    svc1.stop_receiving = AsyncMock()
    await container.stop()
    svc1.stop_streaming.assert_awaited_once()
    svc1.stop_receiving.assert_awaited_once()
    assert container._screen_cast_service is None
