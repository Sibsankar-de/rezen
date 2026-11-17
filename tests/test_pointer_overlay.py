from io import StringIO
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from input_control.pointer_overlay import PointerOverlay, _find_system_python
from input_control.receiver import InputReceiver
from models.input import InputObject, InputType
from screen_cast.pipewire_capture import PipeWireScreenCapture


def test_find_system_python():
    py = _find_system_python()
    assert py is not None


def test_pointer_overlay_lifecycle():
    mock_stdin = StringIO()
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.stdin = mock_stdin

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        overlay = PointerOverlay(color_hex="#00E676", size=18)
        overlay.start(1920, 1080)
        assert overlay._proc is not None
        mock_popen.assert_called_once()
        assert mock_popen.call_args[1]["env"]["GDK_BACKEND"] == "x11"

        overlay.update_position(500, 300)
        assert "move 500 300\n" in mock_stdin.getvalue()

        overlay.show_click_feedback("left", True)
        assert "click left 1\n" in mock_stdin.getvalue()

        overlay.stop()
        assert "quit\n" in mock_stdin.getvalue()
        assert overlay._proc is None




@pytest.mark.asyncio
async def test_input_receiver_normalized_calibration():
    mock_overlay = MagicMock()
    pointer_events = []

    def on_pointer(x: int, y: int, pressed: bool):
        pointer_events.append((x, y, pressed))

    receiver = InputReceiver(
        pointer_overlay=mock_overlay,
        on_remote_pointer=on_pointer,
    )
    receiver._host_screen_size = (1920, 1080)

    # 1. Event with normalized coords 0.5, 0.5 (center)
    event_center = InputObject(
        type=InputType.MOUSE,
        data={"move_abs:0,0:0.500000,0.500000"},
    )
    await receiver._handle_received_event(event_center)

    mock_overlay.update_position.assert_called_with(960, 540)
    assert len(pointer_events) == 1
    assert pointer_events[-1] == (960, 540, False)

    # 2. Event with normalized coords 1.0, 1.0 (bottom-right edge)
    event_br = InputObject(
        type=InputType.MOUSE,
        data={"move_abs:0,0:1.000000,1.000000"},
    )
    await receiver._handle_received_event(event_br)

    mock_overlay.update_position.assert_called_with(1919, 1079)
    assert pointer_events[-1] == (1919, 1079, False)

    # 3. Click event with coordinates and press feedback
    event_click = InputObject(
        type=InputType.MOUSE,
        data={"click:left:1:960,540:0.500000,0.500000"},
    )
    await receiver._handle_received_event(event_click)
    mock_overlay.show_click_feedback.assert_called_with("left", True)
    assert pointer_events[-1] == (960, 540, True)


def test_pipewire_burns_host_pointer_only():
    cap = MagicMock(spec=PipeWireScreenCapture)
    cap._source_width = 1920
    cap._source_height = 1080
    cap._width = 1280
    cap._height = 720
    mock_mouse = MagicMock()
    mock_mouse.position = (400, 200)
    cap._mouse_controller = mock_mouse

    # Create empty frame (all black)
    frame = np.zeros((720, 1280, 4), dtype=np.uint8)
    burned = PipeWireScreenCapture._apply_cursor(cap, frame)

    # In 1280x720 frame, host cursor (400, 200) maps to (267, 133)
    # Check that pixels are non-zero at host cursor position
    assert burned[133, 267].any()

    # Verify no green remote pointer is burned into the frame
    has_green = np.any((burned[:, :, 1] > 200) & (burned[:, :, 2] < 50))
    assert not has_green

