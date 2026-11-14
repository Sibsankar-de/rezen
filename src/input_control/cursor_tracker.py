import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from pynput.mouse import Controller

from settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class HostCursorTracker:
    """Tracks physical host cursor coordinates and emits updates when moved."""

    def __init__(
        self,
        on_cursor_update: Callable[[int, int, bool], Coroutine[Any, Any, None]],
        sync_fps: int | None = None,
    ):
        self._on_cursor_update = on_cursor_update
        self._sync_fps = max(1, sync_fps or settings.HOST_CURSOR_SYNC_FPS)
        self._mouse_controller = Controller()
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_x: int | None = None
        self._last_y: int | None = None

    async def start(self) -> None:
        """Start tracking host cursor movements."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"HostCursorTracker started at {self._sync_fps} FPS.")

    async def stop(self) -> None:
        """Stop tracking host cursor movements."""
        if not self._running:
            return

        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("HostCursorTracker stopped.")

    async def _run_loop(self) -> None:
        interval = 1.0 / self._sync_fps
        while self._running:
            try:
                pos = self._mouse_controller.position
                x = round(pos[0])
                y = round(pos[1])

                if x != self._last_x or y != self._last_y:
                    self._last_x = x
                    self._last_y = y
                    await self._on_cursor_update(x, y, True)

                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except (OSError, RuntimeError) as exc:
                logger.debug(f"HostCursorTracker polling error: {exc}")
                await asyncio.sleep(interval)
