from io import StringIO
from unittest.mock import MagicMock, patch

from input_control.pointer_overlay import PointerOverlay, _find_system_python


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

        overlay.update_position(500, 300)
        assert "move 500 300\n" in mock_stdin.getvalue()

        overlay.show_click_feedback("left", True)
        assert "click left 1\n" in mock_stdin.getvalue()

        overlay.stop()
        assert "quit\n" in mock_stdin.getvalue()
        assert overlay._proc is None
