import asyncio
import os
import sys
from collections.abc import Callable
from typing import Any

from pynput.keyboard import Key, KeyCode, Listener

from input_control.normalizer import KeyNormalizer
from models.input import InputObject, InputType
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
            logger.info("KeyboardCapture is already running.")
            return

        self._loop = asyncio.get_running_loop()
        self._enqueue = enqueue

        session_type = os.environ.get("XDG_SESSION_TYPE", "unknown")
        display = os.environ.get("DISPLAY", "")
        wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
        logger.info(
            f"Initializing KeyboardCapture (OS: {sys.platform}, session: {session_type}, "
            f"DISPLAY: '{display}', WAYLAND_DISPLAY: '{wayland_display}')"
        )

        if session_type.lower() == "wayland":
            logger.warning(
                "Wayland session detected: pynput captures via X11/Xwayland. "
                "Global keystrokes from native Wayland windows may not be delivered to Xwayland."
            )

        self._listner = Listener(
            on_press=self._on_key_press, on_release=self._on_key_release
        )

        self._listner.start()
        logger.info(
            f"KeyboardCapture listener started (backend: {self._listner.__class__.__name__}, "
            f"is_alive: {self._listner.is_alive()})."
        )

    async def stop(self) -> None:
        """Stop the running listner"""
        if self._listner is None or not self._listner.is_alive():
            self._listner = None
            self._pressed_keys.clear()
            logger.info("KeyboardCapture already stopped.")
            return

        logger.info("Stopping KeyboardCapture listener...")
        self._listner.stop()

        try:
            await asyncio.to_thread(self._listner.join, 0.5)
        except Exception:  # noqa: BLE001
            logger.debug("KeyboardCapture listener thread join timed out or failed.")

        self._listner = None
        self._pressed_keys.clear()
        logger.info("KeyboardCapture listener stopped cleanly.")

    def _on_key_press(self, key: Key | KeyCode | None) -> None:
        """Capture key press"""
        try:
            normalized_key = KeyNormalizer.normalize_key(key)
            if not normalized_key:
                logger.warning(f"Key press could not be normalized: {key!r}")
                return

            self._pressed_keys.add(normalized_key)
            logger.info(
                f"[CAPTURE] Key pressed: raw={key!r} -> norm='{normalized_key}' | "
                f"Active keys: {self._pressed_keys}"
            )

            input_object = InputObject(
                type=InputType.KEYBOARD, data=set(self._pressed_keys)
            )
            if self._loop is not None and not self._loop.is_closed():
                self._loop.call_soon_threadsafe(self._enqueue, input_object)
            else:
                logger.warning("Event loop is not running or closed; dropping key press event.")
        except Exception:
            logger.exception(f"Error handling key press for {key!r}")

    def _on_key_release(self, key: Key | KeyCode | None) -> None:
        """Handle release pressed key"""
        try:
            normalized_key = KeyNormalizer.normalize_key(key)
            if normalized_key:
                self._pressed_keys.discard(normalized_key)
                logger.info(
                    f"[CAPTURE] Key released: raw={key!r} -> norm='{normalized_key}' | "
                    f"Active keys: {self._pressed_keys}"
                )
            else:
                logger.debug(f"[CAPTURE] Unnormalized key released: {key!r}")
        except Exception:
            logger.exception(f"Error handling key release for {key!r}")

