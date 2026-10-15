import asyncio
from typing import Callable, Any

from pynput.keyboard import Key, KeyCode, Listener

from models.input import InputType, InputObject
from input_control.normalizer import KeyNormalizer
from utils.logger import get_logger

logger = get_logger(__name__)


class KeyboardCapture:
    """Capture keyboard events using pynput"""

    def __init__(self):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._listner: Listener | None = None
        self._pressed_keys: set[str] = set()

    async def start(self, enqueue: Callable[[InputObject], Any]) -> None:
        """Start the keyboard listner in a blocking thread"""
        if self._listner is not None and self._listner.is_alive():
            return

        self._loop = asyncio.get_running_loop()
        self._enqueue = enqueue

        self._listner = Listener(
            on_press=self._on_key_press, on_release=self._on_key_release
        )

        self._listner.start()

    async def stop(self) -> None:
        """Stop the running listner"""
        if self._listner is None or not self._listner.is_alive():
            self._listner = None
            self._pressed_keys.clear()
            return

        self._listner.stop()

        await asyncio.to_thread(self._listner.join)

        self._listner = None
        self._pressed_keys.clear()

    def _on_key_press(self, key: Key | KeyCode | None) -> None:
        """Capture key press"""
        normalized_key = KeyNormalizer.normalize_key(key)
        if normalized_key:
            self._pressed_keys.add(normalized_key)

        input_object = InputObject(type=InputType.KEYBOARD, data=set(self._pressed_keys))
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._enqueue, input_object)

    def _on_key_release(self, key: Key | KeyCode | None) -> None:
        """Handle release pressed key"""
        normalized_key = KeyNormalizer.normalize_key(key)
        if normalized_key:
            self._pressed_keys.discard(normalized_key)
