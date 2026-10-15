import os
import sys
import time
from typing import Any

try:
    import evdev
    from evdev import ecodes
except ImportError:
    evdev = None
    ecodes = None

from pynput.keyboard import Controller

from input_control.normalizer import KeyNormalizer
from models.input import InputObject
from utils.logger import get_logger

logger = get_logger(__name__)


KEY_PRESS_DELAY_SECONDS = 0.02


class KeyboardController:
    """Apply keyboard events on the screen using evdev UInput (Wayland/X11) or pynput."""

    def __init__(self):
        session_type = self._log_environment()
        self._uinput: Any | None = None
        self._keyboard_controller: Controller | None = None
        self._backend = "pynput"

        self._init_backend(session_type)

    def apply(self, input_object: InputObject) -> None:
        """Apply key set sequentially."""
        logger.info(
            f"[CONTROLLER] Applying input object ({self._backend}): {input_object.data}"
        )
        if self._backend == "evdev" and self._uinput is not None:
            self._apply_evdev(input_object.data)
        else:
            self._apply_pynput(input_object.data)

    def close(self) -> None:
        """Release virtual device resources."""
        self._close_uinput()

    def _log_environment(self) -> str:
        """Log runtime platform and session diagnostics."""
        session_type = os.environ.get("XDG_SESSION_TYPE", "unknown")
        display = os.environ.get("DISPLAY", "")
        wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
        logger.info(
            f"Initializing KeyboardController (OS: {sys.platform}, session: {session_type}, "
            f"DISPLAY: '{display}', WAYLAND_DISPLAY: '{wayland_display}')"
        )
        return session_type

    def _init_backend(self, session_type: str) -> None:
        """Initialize the preferred backend: evdev on Linux, else pynput."""
        if sys.platform.startswith("linux") and evdev is not None:
            if self._init_evdev():
                return

        self._init_pynput(session_type)

    def _init_evdev(self) -> bool:
        """Attempt to initialize evdev UInput virtual device."""
        try:
            self._uinput = evdev.UInput(name="rezen-virtual-keyboard")
            self._backend = "evdev"
            logger.info(
                "[CONTROLLER] Successfully initialized evdev UInput virtual keyboard device."
            )
            return True
        except (PermissionError, OSError) as e:
            logger.warning(
                f"[CONTROLLER] Cannot initialize evdev UInput ({e}). "
                "To enable native Wayland input injection via evdev, configure uinput permissions:\n"
                '    echo \'KERNEL=="uinput", GROUP="input", MODE="0660"\' | sudo tee /etc/udev/rules.d/99-uinput.rules\n'
                "    sudo usermod -aG input $USER\n"
                "Falling back to pynput Controller."
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"[CONTROLLER] Unexpected error initializing evdev UInput ({e}). "
                "Falling back to pynput."
            )
        return False

    def _init_pynput(self, session_type: str) -> None:
        """Initialize pynput Controller."""
        self._backend = "pynput"
        if session_type.lower() == "wayland":
            logger.warning(
                "Wayland session detected: pynput controller simulates events via X11/XTest. "
                "Synthetic keystrokes may only be received by X11/Xwayland windows, and "
                "native Wayland windows might not receive them unless they use Xwayland."
            )
        self._keyboard_controller = Controller()

    def _apply_evdev(self, raw_keys: set[str] | list[str]) -> None:
        """Sequentially press and release keys using evdev UInput."""
        codes = [KeyNormalizer.denormalize_to_evdev(k) for k in raw_keys]
        valid_codes = [c for c in codes if c is not None]

        if not valid_codes:
            logger.warning(
                f"[CONTROLLER] [evdev] No valid key codes could be resolved from: {raw_keys}"
            )
            return

        ev_key = ecodes.EV_KEY
        pressed = self._press_evdev_keys(valid_codes, ev_key)
        self._uinput.syn()

        time.sleep(KEY_PRESS_DELAY_SECONDS)

        self._release_evdev_keys(reversed(pressed), ev_key)
        self._uinput.syn()

    def _press_evdev_keys(self, codes: list[int], ev_key: int) -> list[int]:
        """Press evdev keys sequentially and return pressed codes."""
        pressed: list[int] = []
        for code in codes:
            try:
                self._uinput.write(ev_key, code, 1)
                pressed.append(code)
                name = ecodes.KEY.get(code, code) if ecodes else code
                logger.info(f"[CONTROLLER] [evdev] Pressed key code: {code} ({name})")
            except Exception:
                logger.exception(
                    f"[CONTROLLER] [evdev] Failed to press key code {code}"
                )
                break
        return pressed

    def _release_evdev_keys(self, codes: Any, ev_key: int) -> None:
        """Release evdev keys in reverse order."""
        for code in codes:
            try:
                self._uinput.write(ev_key, code, 0)
                name = ecodes.KEY.get(code, code) if ecodes else code
                logger.info(f"[CONTROLLER] [evdev] Released key code: {code} ({name})")
            except Exception:
                logger.exception(
                    f"[CONTROLLER] [evdev] Failed to release key code {code}"
                )

    def _apply_pynput(self, raw_keys: set[str] | list[str]) -> None:
        """Sequentially press and release keys using pynput Controller."""
        keys = [KeyNormalizer.denormalize_key(key) for key in raw_keys]
        valid_keys = [k for k in keys if k is not None]

        if not valid_keys:
            logger.warning(
                f"[CONTROLLER] [pynput] No valid keys could be resolved from: {raw_keys}"
            )
            return

        if self._keyboard_controller is None:
            logger.warning("[CONTROLLER] No keyboard controller available.")
            return

        pressed = self._press_pynput_keys(valid_keys)
        time.sleep(KEY_PRESS_DELAY_SECONDS)
        self._release_pynput_keys(reversed(pressed))

    def _press_pynput_keys(self, keys: list[Any]) -> list[Any]:
        """Press pynput keys sequentially."""
        pressed: list[Any] = []
        for key in keys:
            try:
                self._keyboard_controller.press(key)
                pressed.append(key)
                logger.info(f"[CONTROLLER] [pynput] Pressed key: {key!r}")
            except Exception:
                logger.exception(f"[CONTROLLER] [pynput] Failed to press key {key!r}")
                break
        return pressed

    def _release_pynput_keys(self, keys: Any) -> None:
        """Release pynput keys in reverse order."""
        for key in keys:
            try:
                self._keyboard_controller.release(key)
                logger.info(f"[CONTROLLER] [pynput] Released key: {key!r}")
            except Exception:
                logger.exception(f"[CONTROLLER] [pynput] Failed to release key {key!r}")

    def _close_uinput(self) -> None:
        """Safely close uinput virtual device descriptor."""
        if self._uinput is not None:
            try:
                self._uinput.close()
            except (OSError, RuntimeError) as e:
                logger.debug(f"[CONTROLLER] Error closing uinput device: {e}")
            self._uinput = None
