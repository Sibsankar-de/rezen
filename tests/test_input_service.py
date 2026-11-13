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
    streamer.start.assert_awaited_once_with(service._handle_send_event, renderer=None)

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

    # Mock keyboard and mouse capture start/stop to avoid spawning real listener threads
    streamer._keyboard_capture.start = AsyncMock()
    streamer._keyboard_capture.stop = AsyncMock()
    streamer._mouse_capture.start = AsyncMock()
    streamer._mouse_capture.stop = AsyncMock()

    await streamer.start(mock_send)

    event1 = InputObject(type=InputType.KEYBOARD, data={"char:z"})
    streamer._enqueue_event(event1)
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


def test_evdev_key_normalizer_and_denormalizer():
    from evdev import ecodes

    from input_control.normalizer import KeyNormalizer

    # Test evdev to normalized string
    assert KeyNormalizer.normalize_evdev_key(ecodes.KEY_A) == "char:a"
    assert KeyNormalizer.normalize_evdev_key(ecodes.KEY_1) == "char:1"
    assert KeyNormalizer.normalize_evdev_key(ecodes.KEY_ENTER) == "special:enter"
    assert KeyNormalizer.normalize_evdev_key(ecodes.KEY_LEFTSHIFT) == "special:shift"
    assert KeyNormalizer.normalize_evdev_key(999999) is None

    # Test normalized string to evdev
    assert KeyNormalizer.denormalize_to_evdev("char:a") == ecodes.KEY_A
    assert KeyNormalizer.denormalize_to_evdev("char:A") == ecodes.KEY_A
    assert KeyNormalizer.denormalize_to_evdev("char:1") == ecodes.KEY_1
    assert KeyNormalizer.denormalize_to_evdev("special:enter") == ecodes.KEY_ENTER
    assert KeyNormalizer.denormalize_to_evdev("special:shift") == ecodes.KEY_LEFTSHIFT
    assert KeyNormalizer.denormalize_to_evdev("special:shift_l") == ecodes.KEY_LEFTSHIFT
    assert KeyNormalizer.denormalize_to_evdev("special:leftshift") == ecodes.KEY_LEFTSHIFT
    assert KeyNormalizer.denormalize_to_evdev("KEY_A") == ecodes.KEY_A
    assert KeyNormalizer.denormalize_to_evdev("unknown:foo") is None


def test_keyboard_controller_evdev_apply():
    from evdev import ecodes

    from input_control.keyboard_controller import KeyboardController

    controller = KeyboardController()
    mock_uinput = MagicMock()
    controller._uinput = mock_uinput
    controller._backend = "evdev"

    event = InputObject(type=InputType.KEYBOARD, data=["char:x", "char:y"])
    controller.apply(event)

    # Verify write calls: press x (1), press y (1), syn, release y (0), release x (0), syn
    writes = mock_uinput.write.call_args_list
    assert len(writes) == 4
    # Press phase
    assert writes[0] == ((ecodes.EV_KEY, ecodes.KEY_X, 1),)
    assert writes[1] == ((ecodes.EV_KEY, ecodes.KEY_Y, 1),)
    # Release phase in reverse order
    assert writes[2] == ((ecodes.EV_KEY, ecodes.KEY_Y, 0),)
    assert writes[3] == ((ecodes.EV_KEY, ecodes.KEY_X, 0),)
    assert mock_uinput.syn.call_count == 2

    controller.close()
    mock_uinput.close.assert_called_once()
    assert controller._uinput is None


@pytest.mark.asyncio
async def test_keyboard_capture_evdev_flow():
    import asyncio

    from evdev import ecodes

    from input_control.keyboard_capture import KeyboardCapture

    kc = KeyboardCapture()
    captured_events = []

    def mock_enqueue(event: InputObject):
        captured_events.append(event)

    # Create a mock evdev device
    mock_dev = MagicMock()
    mock_dev.name = "Mock Keyboard"
    mock_dev.path = "/dev/input/event99"

    class MockEvent:
        def __init__(self, type_, code, value):
            self.type = type_
            self.code = code
            self.value = value

    async def mock_async_read_loop():
        # Press 'a'
        yield MockEvent(ecodes.EV_KEY, ecodes.KEY_A, 1)
        await asyncio.sleep(0.01)
        # Release 'a'
        yield MockEvent(ecodes.EV_KEY, ecodes.KEY_A, 0)
        await asyncio.sleep(0.01)

    mock_dev.async_read_loop = mock_async_read_loop

    # Force discovery to return mock device
    kc._discover_evdev_keyboards = MagicMock(return_value=[mock_dev])

    await kc.start(mock_enqueue)
    assert kc._backend == "evdev"
    assert len(kc._evdev_tasks) == 1

    await asyncio.sleep(0.05)
    assert len(captured_events) >= 1
    assert "char:a" in captured_events[0].data

    await kc.stop()
    assert len(kc._evdev_tasks) == 0
    assert len(kc._evdev_devices) == 0


@pytest.mark.asyncio
async def test_mouse_capture_focus_gate_and_translation():
    import asyncio
    from input_control.mouse_capture import MouseCapture

    class MockRenderer:
        def __init__(self, focused=True, geom=(100, 100, 800, 600), src=(1600, 1200)):
            self.is_focused = focused
            self.window_geometry = geom
            self.source_size = src

    mc = MouseCapture()
    captured = []

    def mock_enqueue(event: InputObject):
        captured.append(event)

    renderer = MockRenderer(focused=True, geom=(100, 100, 800, 600), src=(1600, 1200))
    await mc.start(mock_enqueue, renderer=renderer)

    # In-bounds move_abs
    # screen (500, 400) -> rel (400, 300) -> scaled: 400 * 1600 / 800 = 800, 300 * 1200 / 600 = 600
    mc._on_pynput_move(500, 400)
    await asyncio.sleep(0.01)
    assert len(captured) == 1
    assert captured[0].data == {"move_abs:800,600"}

    # Out-of-bounds move_abs (screen 50, 50 is outside window at 100, 100)
    mc._on_pynput_move(50, 50)
    await asyncio.sleep(0.01)
    assert len(captured) == 1

    # Unfocused -> drop all events
    renderer.is_focused = False
    mc._on_pynput_move(500, 400)
    await asyncio.sleep(0.01)
    assert len(captured) == 1

    await mc.stop()


@pytest.mark.asyncio
async def test_keyboard_capture_focus_gate():
    import asyncio
    from input_control.keyboard_capture import KeyboardCapture

    class MockRenderer:
        def __init__(self, focused=True):
            self.is_focused = focused
            self.window_geometry = (0, 0, 800, 600)
            self.source_size = (1280, 720)

    kc = KeyboardCapture()
    captured = []

    def mock_enqueue(event: InputObject):
        captured.append(event)

    renderer = MockRenderer(focused=False)
    await kc.start(mock_enqueue, renderer=renderer)

    # Press while unfocused -> dropped
    kc._handle_key_press("char:a", "test")
    assert len(captured) == 0

    # Focus window
    renderer.is_focused = True
    kc._handle_key_press("char:a", "test")
    await asyncio.sleep(0.01)
    assert len(captured) == 1
    assert "char:a" in captured[0].data

    await kc.stop()


@pytest.mark.asyncio
async def test_mouse_capture_clicks_and_scrolls_inside_and_outside_video():
    import asyncio
    from pynput.mouse import Button
    from input_control.mouse_capture import MouseCapture

    class MockRenderer:
        def __init__(self):
            self.is_focused = True
            self.window_geometry = (200, 150, 1000, 500)
            self.source_size = (1920, 1080)

    mc = MouseCapture()
    captured = []

    def mock_enqueue(event: InputObject):
        captured.append(event)

    renderer = MockRenderer()
    await mc.start(mock_enqueue, renderer=renderer)

    # Click outside video (e.g. at 50, 50) -> dropped
    mc._on_pynput_click(50, 50, Button.left, True)
    await asyncio.sleep(0.01)
    assert len(captured) == 0

    # Click inside video (e.g. at 700, 400 -> rel=(500, 250) -> scaled: 500*1920/1000=960, 250*1080/500=540)
    mc._on_pynput_click(700, 400, Button.left, True)
    await asyncio.sleep(0.01)
    assert len(captured) == 2
    assert captured[0].data == {"move_abs:960,540"}
    assert captured[1].data == {"click:left:1"}

    # Scroll outside video -> dropped
    mc._on_pynput_scroll(100, 100, 0, 1)
    await asyncio.sleep(0.01)
    assert len(captured) == 2

    # Scroll inside video
    mc._on_pynput_scroll(700, 400, 0, 1)
    await asyncio.sleep(0.01)
    assert len(captured) == 3
    assert captured[2].data == {"scroll:0,1"}

    await mc.stop()


@pytest.mark.asyncio
async def test_mouse_capture_resizing_dynamic_scaling():
    import asyncio
    from input_control.mouse_capture import MouseCapture

    class MockRenderer:
        def __init__(self):
            self.is_focused = True
            self.window_geometry = (100, 100, 1000, 500)
            self.source_size = (1920, 1080)

    mc = MouseCapture()
    captured = []

    def mock_enqueue(event: InputObject):
        captured.append(event)

    renderer = MockRenderer()
    await mc.start(mock_enqueue, renderer=renderer)

    # Initial move: (600, 350) -> rel=(500, 250) -> host=(960, 540)
    mc._on_pynput_move(600, 350)
    await asyncio.sleep(0.01)
    assert len(captured) == 1
    assert captured[0].data == {"move_abs:960,540"}

    # Resize window: video rendering rectangle becomes 2000x1000 at (50, 50)
    renderer.window_geometry = (50, 50, 2000, 1000)
    # Move: (1050, 550) -> rel=(1000, 500) -> host=(960, 540)
    mc._on_pynput_move(1050, 550)
    await asyncio.sleep(0.01)
    assert len(captured) == 2
    assert captured[1].data == {"move_abs:960,540"}

    await mc.stop()


def test_screen_renderer_is_focused_default_false():
    from screen_cast.renderer import ScreenRenderer
    renderer = ScreenRenderer()
    assert renderer.is_focused is False


def test_mouse_controller_move_abs_and_click():
    from unittest.mock import MagicMock
    from pynput.mouse import Button
    from input_control.mouse_controller import MouseController

    mc = MouseController()
    mock_pynput_ctrl = MagicMock()
    mc._mouse_controller = mock_pynput_ctrl

    # move_abs
    event = InputObject(type=InputType.MOUSE, data={"move_abs:800,600"})
    mc.apply(event)
    assert mock_pynput_ctrl.position == (800, 600)

    # click press
    click_press = InputObject(type=InputType.MOUSE, data={"click:left:1"})
    mc.apply(click_press)
    mock_pynput_ctrl.press.assert_called_once_with(Button.left)

    # click release
    click_release = InputObject(type=InputType.MOUSE, data={"click:left:0"})
    mc.apply(click_release)
    mock_pynput_ctrl.release.assert_called_once_with(Button.left)

    # scroll
    scroll = InputObject(type=InputType.MOUSE, data={"scroll:0,-2"})
    mc.apply(scroll)
    mock_pynput_ctrl.scroll.assert_called_once_with(0, -2)

    mc.close()


def test_mouse_controller_uinput_delta_tracking():
    from unittest.mock import MagicMock
    from input_control.mouse_controller import MouseController

    mc = MouseController()
    mock_uinput = MagicMock()
    mc._uinput = mock_uinput
    mc._mouse_controller = None

    # First event sets anchor
    mc.apply(InputObject(type=InputType.MOUSE, data={"move_abs:500,300"}))
    assert mock_uinput.write.call_count == 0

    # Second event within threshold sends delta dx=5, dy=10
    mc.apply(InputObject(type=InputType.MOUSE, data={"move_abs:505,310"}))
    assert mock_uinput.write.call_count >= 2
    mock_uinput.syn.assert_called()

    mc.close()


def test_renderer_is_window_focused_cached_display():
    from unittest.mock import MagicMock, patch
    import screen_cast.renderer as rend

    mock_disp = MagicMock()
    mock_focus = MagicMock()
    mock_focus.focus.get_wm_name.return_value = "TestWindow"
    mock_disp.get_input_focus.return_value = mock_focus

    with patch.object(rend, "Xlib") as mock_xlib:
        mock_xlib.display.Display.return_value = mock_disp
        rend._xlib_display = None

        res1 = rend._is_window_focused("TestWindow")
        res2 = rend._is_window_focused("TestWindow")

        assert res1 is True
        assert res2 is True
        # Display() should only be called once, not twice
        assert mock_xlib.display.Display.call_count == 1


@pytest.mark.asyncio
async def test_mouse_capture_accurate_boundary_calibration():
    import asyncio
    from input_control.mouse_capture import MouseCapture

    class MockRenderer:
        def __init__(self):
            self.is_focused = True
            self.window_geometry = (100, 100, 960, 540)
            self.source_size = (1920, 1080)

    mc = MouseCapture()
    captured = []

    def mock_enqueue(event: InputObject):
        captured.append(event)

    renderer = MockRenderer()
    await mc.start(mock_enqueue, renderer=renderer)

    # Top-left corner
    mc._on_pynput_move(100, 100)
    await asyncio.sleep(0.01)
    assert captured[-1].data == {"move_abs:0,0"}

    # Center of video
    mc._on_pynput_move(100 + 480, 100 + 270)
    await asyncio.sleep(0.01)
    assert captured[-1].data == {"move_abs:960,540"}

    # Bottom-right inside video
    mc._on_pynput_move(100 + 959, 100 + 539)
    await asyncio.sleep(0.01)
    assert captured[-1].data == {"move_abs:1918,1078"}

    # Right outside video
    mc._on_pynput_move(100 + 960, 100 + 539)
    await asyncio.sleep(0.01)
    assert len(captured) == 3

    await mc.stop()


def test_mouse_capture_relative_move_subpixel_sensitivity():
    from input_control.mouse_capture import MouseCapture

    class MockRenderer:
        def __init__(self):
            self.is_focused = True
            self.window_geometry = (0, 0, 1920, 1080)
            self.source_size = (960, 540)

    mc = MouseCapture()
    mc._renderer = MockRenderer()

    # Scaling down 0.5x: dx=1 should preserve minimum movement dx=1, not 0
    res = mc._translate("move:1,0")
    assert res == "move:1,0"

    res_neg = mc._translate("move:-1,0")
    assert res_neg == "move:-1,0"

    res_y = mc._translate("move:0,1")
    assert res_y == "move:0,1"







