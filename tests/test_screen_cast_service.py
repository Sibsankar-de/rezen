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
    from unittest.mock import call

    service, cm, _, _, _, receiver = screen_cast_setup

    await service.start_receiving()
    receiver.start.assert_awaited_once()
    cm.subscribe.assert_has_awaits([
        call(service._handle_stream_packet),
        call(service._handle_screen_info_packet),
    ])

    await service.stop_receiving()
    cm.unsubscribe.assert_has_awaits([
        call(service._handle_stream_packet),
        call(service._handle_screen_info_packet),
    ])
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


@pytest.mark.asyncio
async def test_screen_cast_service_sends_screen_info_on_start(screen_cast_setup):
    service, cm, cs, _, streamer, _ = screen_cast_setup
    streamer.screen_size = (1920, 1080)

    await service.start_streaming()
    streamer.start.assert_awaited_once()
    cm.subscribe.assert_awaited_once_with(service._handle_streamer_packet)

    # First call to send_to_latest should be SCREEN_INFO
    assert cs.send_to_latest.await_count >= 1
    sent_packet: Packet = cs.send_to_latest.call_args_list[0][0][0]
    assert sent_packet.type == PacketType.SCREEN_INFO
    assert sent_packet.payload == {"width": 1920, "height": 1080}

    await service.stop_streaming()
    cm.unsubscribe.assert_awaited_once_with(service._handle_streamer_packet)


@pytest.mark.asyncio
async def test_screen_cast_service_handles_screen_info_packet(screen_cast_setup):
    service, _, cs, _, _, receiver = screen_cast_setup
    receiver.set_host_resolution = MagicMock()

    conn = cs.latest_connection
    packet = Packet(
        type=PacketType.SCREEN_INFO,
        version="1.0",
        device_id="remote_dev",
        payload={"width": 1920, "height": 1080},
    )

    await service._handle_screen_info_packet(conn, packet)
    receiver.set_host_resolution.assert_called_once_with(1920, 1080)
    receiver.handle_chunk.assert_not_called()


@pytest.mark.asyncio
async def test_screen_cast_service_screen_info_request_flow(screen_cast_setup):
    service, _cm, cs, _, streamer, _receiver = screen_cast_setup
    streamer.screen_size = (2560, 1440)

    # Viewer starting receiving sends SCREEN_INFO_REQUEST
    await service.start_receiving()
    assert cs.send_to_latest.await_count == 1
    req_packet: Packet = cs.send_to_latest.call_args[0][0]
    assert req_packet.type == PacketType.SCREEN_INFO_REQUEST

    # Streamer receives request and replies with SCREEN_INFO
    cs.send_to_latest.reset_mock()
    conn = cs.latest_connection
    await service._handle_streamer_packet(conn, req_packet)

    assert cs.send_to_latest.await_count == 1
    reply_packet: Packet = cs.send_to_latest.call_args[0][0]
    assert reply_packet.type == PacketType.SCREEN_INFO
    assert reply_packet.payload == {"width": 2560, "height": 1440}


def test_verify_connection_packet(screen_cast_setup):
    service, _, cs, _, _, _ = screen_cast_setup

    conn = cs.latest_connection
    pkt = Packet(
        type=PacketType.SCREEN_INFO,
        version="1.0",
        device_id="remote_dev",
        payload={"width": 1920, "height": 1080},
    )

    # Valid packet and matching connection
    assert service._verify_connection_packet(conn, pkt) is True
    assert service._verify_connection_packet(conn, pkt, PacketType.SCREEN_INFO) is True

    # Packet None
    assert service._verify_connection_packet(conn, None) is False

    # Type mismatch
    assert service._verify_connection_packet(conn, pkt, PacketType.SCREEN_FRAME_CHUNK) is False

    # No active latest connection
    cs.latest_connection = None
    assert service._verify_connection_packet(conn, pkt) is False

    # Mismatched connection
    other_conn = MagicMock(spec=Connection)
    other_conn.id = "conn_other"
    other_conn.device_id = "other_dev"
    cs.latest_connection = conn
    assert service._verify_connection_packet(other_conn, pkt) is False


@pytest.mark.asyncio
async def test_host_cursor_packet_send_and_receive(screen_cast_setup):
    service, _, cs, _, _, receiver = screen_cast_setup
    conn = cs.latest_connection

    # Test send
    await service._send_host_cursor(250, 450, True)
    cs.send_to_latest.assert_awaited_once()
    sent_pkt = cs.send_to_latest.call_args[0][0]
    assert sent_pkt.type == PacketType.HOST_CURSOR
    assert sent_pkt.payload == {"x": 250, "y": 450, "visible": True}

    # Test receive
    receiver.set_host_cursor = MagicMock()
    recv_pkt = Packet(
        type=PacketType.HOST_CURSOR,
        version="1.0",
        device_id="remote_dev",
        payload={"x": 500, "y": 300, "visible": True},
    )
    await service._handle_host_cursor_packet(conn, recv_pkt)
    receiver.set_host_cursor.assert_called_once_with(500, 300, True)
