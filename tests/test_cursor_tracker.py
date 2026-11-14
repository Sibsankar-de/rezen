import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from input_control.cursor_tracker import HostCursorTracker


@pytest.mark.asyncio
async def test_cursor_tracker_polls_and_emits_position():
    mock_callback = AsyncMock()
    mock_mouse = MagicMock()
    mock_mouse.position = (100, 200)

    tracker = HostCursorTracker(mock_callback, sync_fps=100)
    tracker._mouse_controller = mock_mouse

    await tracker.start()
    assert tracker._running is True
    await asyncio.sleep(0.05)

    mock_callback.assert_awaited()
    assert mock_callback.call_args[0] == (100, 200, True)

    mock_callback.reset_mock()
    mock_mouse.position = (150, 250)
    await asyncio.sleep(0.05)

    mock_callback.assert_awaited_with(150, 250, True)

    await tracker.stop()
    assert tracker._running is False
