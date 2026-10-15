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
from models.input import InputObject, InputType
from protocol.packet import Packet, PacketType
from protocol.serializer import PacketSerializer
from services.input_service import InputService


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
def input_service_setup(mock_device):
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
    receiver.receive_input = AsyncMock()

    service = InputService(
        connection_manager=cm,
        connection_service=cs,
        device_service=ds,
        input_streamer=streamer,
        input_receiver=receiver,
    )

    return service, cm, cs, ds, streamer, receiver


@pytest.mark.asyncio
async def test_start_and_stop_streamer(input_service_setup):
    service, _, _, _, streamer, _ = input_service_setup

    await service.start_streamer()
    streamer.start.assert_awaited_once_with(service._handle_send_event)

    await service.stop_streamer()
    streamer.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_and_stop_receiver(input_service_setup):
    service, cm, _, _, _, receiver = input_service_setup

    await service.start_receiver()
    receiver.start.assert_awaited_once()
    cm.subscribe.assert_awaited_once_with(service._handle_input_packet)

    await service.stop_receiver()
    cm.unsubscribe.assert_awaited_once_with(service._handle_input_packet)
    receiver.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_send_event(input_service_setup, mock_device):
    service, _, cs, _, _, _ = input_service_setup

    event = InputObject(
        type=InputType.KEYBOARD,
        data={"char:a", "special:shift"},
    )

    await service._handle_send_event(event)
    cs.send_to_latest.assert_awaited_once()

    sent_packet: Packet = cs.send_to_latest.call_args[0][0]
    assert sent_packet.type == PacketType.INPUT_EVENT
    assert sent_packet.version == "1.0"
    assert sent_packet.device_id == mock_device.id
    assert sent_packet.payload == event


@pytest.mark.asyncio
async def test_handle_input_packet_valid_object(input_service_setup):
    service, _, cs, _, _, receiver = input_service_setup

    conn = cs.latest_connection
    event = InputObject(
        type=InputType.KEYBOARD,
        data={"char:k"},
    )
    packet = Packet(
        type=PacketType.INPUT_EVENT,
        version="1.0",
        device_id="remote_dev",
        payload=event,
    )

    await service._handle_input_packet(conn, packet)
    receiver.receive_input.assert_awaited_once_with(event)


@pytest.mark.asyncio
async def test_handle_input_packet_dict_payload(input_service_setup):
    service, _, cs, _, _, receiver = input_service_setup

    conn = cs.latest_connection
    payload_dict = {
        "type": "keyboard",
        "data": ["char:b", "char:c"],
    }
    packet = Packet(
        type=PacketType.INPUT_EVENT,
        version="1.0",
        device_id="remote_dev",
        payload=payload_dict,
    )

    await service._handle_input_packet(conn, packet)
    receiver.receive_input.assert_awaited_once()
    received_obj: InputObject = receiver.receive_input.call_args[0][0]
    assert isinstance(received_obj, InputObject)
    assert received_obj.type == InputType.KEYBOARD
    assert received_obj.data == {"char:b", "char:c"}


@pytest.mark.asyncio
async def test_handle_input_packet_mismatched_connection_ignored(input_service_setup):
    service, _, _, _, _, receiver = input_service_setup

    other_conn = MagicMock(spec=Connection)
    other_conn.id = "conn_other"

    packet = Packet(
        type=PacketType.INPUT_EVENT,
        version="1.0",
        device_id="other_dev",
        payload={"type": "keyboard", "data": ["char:x"]},
    )

    await service._handle_input_packet(other_conn, packet)
    receiver.receive_input.assert_not_called()


@pytest.mark.asyncio
async def test_container_input_service_property():
    container = Container()

    bc = MagicMock()
    bc.stop = AsyncMock()
    cm = MagicMock()
    cm.stop = AsyncMock()
    ds = MagicMock()

    container._broadcaster = bc
    container._connection_manager = cm
    container._device_service = ds

    svc1 = container.input_service
    svc2 = container.input_service
    assert svc1 is svc2
    assert isinstance(svc1, InputService)

    svc1.stop_streamer = AsyncMock()
    svc1.stop_receiver = AsyncMock()
    await container.stop()
    svc1.stop_streamer.assert_awaited_once()
    svc1.stop_receiver.assert_awaited_once()
    assert container._input_service is None


def test_packet_serialization_with_input_object():
    event = InputObject(type=InputType.KEYBOARD, data={"char:x", "special:ctrl"})
    packet = Packet(
        type=PacketType.INPUT_EVENT,
        version="1.0",
        device_id="dev_1",
        payload=event,
    )

    raw_bytes = PacketSerializer.dumps(packet)
    assert isinstance(raw_bytes, bytes)

    deserialized = PacketSerializer.loads(raw_bytes)
    assert deserialized.type == PacketType.INPUT_EVENT
    assert deserialized.version == "1.0"
    assert deserialized.device_id == "dev_1"
    assert deserialized.payload["type"] == "keyboard"
    assert set(deserialized.payload["data"]) == {"char:x", "special:ctrl"}


def test_key_normalizer_and_denormalizer():
    from pynput.keyboard import Key, KeyCode

    from input_control.normalizer import KeyNormalizer

    assert KeyNormalizer.normalize_key(Key.enter) == "special:enter"
    assert KeyNormalizer.normalize_key(KeyCode.from_char("a")) == "char:a"
    assert KeyNormalizer.normalize_key(KeyCode.from_vk(65)) == "vk:65"
    assert KeyNormalizer.normalize_key(None) is None

    assert KeyNormalizer.denormalize_key("special:enter") == Key.enter
    assert KeyNormalizer.denormalize_key("char:a").char == "a"
    assert KeyNormalizer.denormalize_key("vk:65").vk == 65
    assert KeyNormalizer.denormalize_key("invalid") is None
    assert KeyNormalizer.denormalize_key("unknown:foo") is None


@pytest.mark.asyncio
async def test_keyboard_capture_press_and_release():
    import asyncio

    from pynput.keyboard import KeyCode

    from input_control.keyboard_capture import KeyboardCapture

    kc = KeyboardCapture()
    captured_events = []

    def mock_enqueue(event: InputObject):
        captured_events.append(event)

    await kc.start(mock_enqueue)
    kc._on_key_press(KeyCode.from_char("x"))
    await asyncio.sleep(0.01)
    assert len(captured_events) == 1
    assert "char:x" in captured_events[0].data

    kc._on_key_release(KeyCode.from_char("x"))
    assert "char:x" not in kc._pressed_keys

    await kc.stop()
    assert kc._pressed_keys == set()


@pytest.mark.asyncio
async def test_input_streamer_and_receiver_flow():
    import asyncio

    from input_control.receiver import InputReceiver
    from input_control.streamer import InputStreamer

    streamer = InputStreamer()
    sent_events = []

    async def mock_send(event: InputObject):
        sent_events.append(event)

    # Mock keyboard capture start/stop to avoid spawning a real listener thread
    streamer._keyboard_capture.start = AsyncMock()
    streamer._keyboard_capture.stop = AsyncMock()

    await streamer.start(mock_send)

    event1 = InputObject(type=InputType.KEYBOARD, data={"char:z"})
    streamer._handle_keyboard_input(event1)
    await asyncio.sleep(0.05)

    assert len(sent_events) == 1
    assert sent_events[0] == event1

    await streamer.stop()
    assert not streamer._running

    # Test InputReceiver
    receiver = InputReceiver()
    receiver._keyboard_controller.apply = MagicMock()

    await receiver.start()
    await receiver.receive_input(event1)
    await asyncio.sleep(0.05)

    receiver._keyboard_controller.apply.assert_called_once_with(event1)
    await receiver.stop()
    assert not receiver._running


def test_keyboard_controller_sequential_apply():
    from input_control.keyboard_controller import KeyboardController

    controller = KeyboardController()
    controller._keyboard_controller = MagicMock()

    # Pass sequential keys: 'a', 'b', 'c'
    event = InputObject(type=InputType.KEYBOARD, data=["char:a", "char:b", "char:c"])
    controller.apply(event)

    call_order = [call[0][0].char for call in controller._keyboard_controller.press.call_args_list]
    assert call_order == ["a", "b", "c"]
    release_order = [call[0][0].char for call in controller._keyboard_controller.release.call_args_list]
    assert release_order == ["c", "b", "a"]


