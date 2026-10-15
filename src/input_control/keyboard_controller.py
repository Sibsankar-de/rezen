import os
import sys
import time
from typing import Any

from pynput.keyboard import Controller

from input_control.normalizer import KeyNormalizer
from models.input import InputObject
from utils.logger import get_logger

logger = get_logger(__name__)


class KeyboardController:
    """Apply keyboard events on the screen"""

    def __init__(self):
        session_type = os.environ.get("XDG_SESSION_TYPE", "unknown")
        display = os.environ.get("DISPLAY", "")
        wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
        logger.info(
            f"Initializing KeyboardController (OS: {sys.platform}, session: {session_type}, "
            f"DISPLAY: '{display}', WAYLAND_DISPLAY: '{wayland_display}')"
        )
        if session_type.lower() == "wayland":
            logger.warning(
                "Wayland session detected: pynput controller simulates events via X11/XTest. "
                "Synthetic keystrokes may only be received by X11/Xwayland windows, and "
                "native Wayland windows might not receive them unless they use Xwayland."
            )
        self._keyboard_controller = Controller()

    def apply(self, input_object: InputObject) -> None:
        """Apply key set"""
        logger.info(f"[CONTROLLER] Applying input object: {input_object.data}")
        denorm_keys = [KeyNormalizer.denormalize_key(key) for key in input_object.data]
        valid_keys = [k for k in denorm_keys if k is not None]

        if not valid_keys:
            logger.warning(
                f"[CONTROLLER] No valid keys could be resolved from: {input_object.data}"
            )
            return

        pressed: list[Any] = []
        for key in valid_keys:
            try:
                self._keyboard_controller.press(key)
                pressed.append(key)
                logger.info(f"[CONTROLLER] Pressed key: {key!r}")
            except Exception:
                logger.exception(f"[CONTROLLER] Failed to press key {key!r}")
                break

        # Brief delay to allow the OS and active window event loop to register the keydown
        time.sleep(0.02)

        # Release keys in reverse order (characters released first, modifiers last)
        for key in reversed(pressed):
            try:
                self._keyboard_controller.release(key)
                logger.info(f"[CONTROLLER] Released key: {key!r}")
            except Exception:
                logger.exception(f"[CONTROLLER] Failed to release key {key!r}")
