from unittest.mock import MagicMock, patch

from input_control.pointer_overlay import PointerOverlay, _build_cursor_shape_rects


def test_build_cursor_shape_rects():
    rects_default = _build_cursor_shape_rects(24)
    assert len(rects_default) == 12
    assert rects_default[0] == (0, 0, 2, 2)

    rects_scaled = _build_cursor_shape_rects(48)
    assert len(rects_scaled) == 12
    assert rects_scaled[0] == (0, 0, 4, 4)


def test_pointer_overlay_lifecycle():
    with patch("threading.Thread") as mock_thread_cls:
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        overlay = PointerOverlay(color_hex="#00E676", size=18)
        overlay.start(1920, 1080)
        assert overlay._thread is not None
        mock_thread.start.assert_called_once()

        overlay.update_position(500, 300)
        assert overlay._queue.get_nowait() == ("move", 500, 300)

        overlay.show_click_feedback("left", True)
        assert overlay._queue.get_nowait() == ("click", "left", True)

        overlay.stop()
        assert overlay._thread is None
