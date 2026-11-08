import os
import sys
from typing import Any

try:
    import evdev
    from evdev import ecodes
except ImportError:
    evdev = None
    ecodes = None

from pynput.mouse import Button, Controller

from models.input import InputObject
from utils.logger import get_logger

logger = get_logger(__name__)


class MouseController:
    """Apply mouse events using evdev UInput (Wayland/X11) or pynput."""

    def __init__(self):
        session_type = self._log_environment()
        self._uinput: Any | None = None
        self._mouse_controller: Controller | None = None
        self._backend = "pynput"

        self._init_backend(session_type)

    def apply(self, input_object: InputObject) -> None:
        """Apply a mouse event encoded in input_object.data."""
        for encoded in input_object.data:
            self._apply_event(encoded)

    def close(self) -> None:
        """Release virtual device resources."""
        self._close_uinput()

    def _log_environment(self) -> str:
        session_type = os.environ.get("XDG_SESSION_TYPE", "unknown")
        display = os.environ.get("DISPLAY", "")
        wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
        logger.info(
            f"Initializing MouseController (OS: {sys.platform}, session: {session_type}, "
            f"DISPLAY: '{display}', WAYLAND_DISPLAY: '{wayland_display}')"
        )
        return session_type

    def _init_backend(self, session_type: str) -> None:
        try:
            self._init_pynput(session_type)
            return
        except Exception as exc:
            logger.warning(
                f"[CONTROLLER] Cannot initialize pynput mouse controller ({exc}). "
                "Falling back to evdev UInput if available."
            )

        if sys.platform.startswith("linux") and evdev is not None:
            if self._init_evdev():
                return

    def _init_evdev(self) -> bool:
        """Attempt to initialize an evdev UInput virtual mouse device."""
        if ecodes is None:
            return False

        _UInputError: type[Exception] = getattr(evdev, "UInputError", None) or type(
            "_UInputError", (Exception,), {}
        )

        events = {
            ecodes.EV_REL: [
                ecodes.REL_X,
                ecodes.REL_Y,
                ecodes.REL_WHEEL,
                ecodes.REL_HWHEEL,
            ],
            ecodes.EV_KEY: [
                ecodes.BTN_LEFT,
                ecodes.BTN_RIGHT,
                ecodes.BTN_MIDDLE,
            ],
        }

        try:
            self._uinput = evdev.UInput(events=events, name="rezen-virtual-mouse")
            self._backend = "evdev"
            logger.info(
                "[CONTROLLER] Successfully initialized evdev UInput virtual mouse device."
            )
            return True
        except (PermissionError, OSError, _UInputError) as e:
            logger.warning(
                f"[CONTROLLER] Cannot initialize evdev mouse UInput ({e}). "
                "To enable native Wayland mouse injection via evdev, configure uinput permissions:\n"
                '    echo \'KERNEL=="uinput", GROUP="input", MODE="0660"\' | sudo tee /etc/udev/rules.d/99-uinput.rules\n'
                "    sudo usermod -aG input $USER\n"
                "(then log out and back in, or run: sudo udevadm control --reload-rules && sudo udevadm trigger)\n"
                "Falling back to pynput Controller."
            )
        except Exception as e:
            logger.warning(
                f"[CONTROLLER] Unexpected error initializing evdev mouse UInput ({e}). "
                "Falling back to pynput."
            )
        return False

    def _init_pynput(self, session_type: str) -> None:
        self._backend = "pynput"
        if session_type.lower() == "wayland":
            logger.warning(
                "Wayland session detected: pynput mouse controller simulates events via X11/XTest. "
                "Synthetic mouse events may only be received by X11/Xwayland windows."
            )
        self._mouse_controller = Controller()

    def _apply_event(self, encoded: str) -> None:
        """Decode and dispatch a single mouse event string."""
        if not encoded or ":" not in encoded:
            logger.warning(f"[CONTROLLER] Malformed mouse event: {encoded!r}")
            return

        kind, _, rest = encoded.partition(":")

        try:
            if kind == "move":
                dx, dy = _parse_int_pair(rest)
                self._do_move(dx, dy)
            elif kind == "move_abs":
                x, y = _parse_int_pair(rest)
                self._do_move_abs(x, y)
            elif kind == "click":
                btn_name, _, state = rest.partition(":")
                pressed = state.strip() == "1"
                self._do_click(btn_name, pressed)
            elif kind == "scroll":
                dx, dy = _parse_int_pair(rest)
                self._do_scroll(dx, dy)
            else:
                logger.warning(f"[CONTROLLER] Unknown mouse event kind: {kind!r}")
        except Exception:
            logger.exception(f"[CONTROLLER] Failed to apply mouse event: {encoded!r}")

    def _do_move(self, dx: int, dy: int) -> None:
        logger.debug(f"[CONTROLLER] Mouse move rel ({dx}, {dy}) via {self._backend}")
        if self._mouse_controller is not None:
            self._mouse_controller.move(dx, dy)
        elif self._backend == "evdev" and self._uinput is not None:
            self._uinput.write(ecodes.EV_REL, ecodes.REL_X, dx)
            self._uinput.write(ecodes.EV_REL, ecodes.REL_Y, dy)
            self._uinput.syn()

    def _do_move_abs(self, x: int, y: int) -> None:
        logger.debug(f"[CONTROLLER] Mouse move abs ({x}, {y}) via {self._backend}")
        if self._mouse_controller is not None:
            self._mouse_controller.position = (x, y)
        elif self._backend == "evdev" and self._uinput is not None:
            logger.warning(
                f"[CONTROLLER] Cannot apply move_abs({x}, {y}) using evdev relative-only mouse."
            )

    def _do_click(self, btn_name: str, pressed: bool) -> None:
        logger.debug(
            f"[CONTROLLER] Mouse {'press' if pressed else 'release'} {btn_name!r} via {self._backend}"
        )
        if self._mouse_controller is not None:
            button = _BTN_NAME_TO_PYNPUT.get(btn_name)
            if button is None:
                logger.warning(f"[CONTROLLER] Unknown button for pynput: {btn_name!r}")
                return
            if pressed:
                self._mouse_controller.press(button)
            else:
                self._mouse_controller.release(button)
            return

        if self._backend == "evdev" and self._uinput is not None:
            code = _BTN_NAME_TO_EVDEV.get(btn_name)
            if code is None:
                logger.warning(f"[CONTROLLER] Unknown button for evdev: {btn_name!r}")
                return
            self._uinput.write(ecodes.EV_KEY, code, 1 if pressed else 0)
            self._uinput.syn()

    def _do_scroll(self, dx: int, dy: int) -> None:
        logger.debug(f"[CONTROLLER] Mouse scroll ({dx}, {dy}) via {self._backend}")
        if self._mouse_controller is not None:
            self._mouse_controller.scroll(dx, dy)
        elif self._backend == "evdev" and self._uinput is not None:
            if dy != 0:
                self._uinput.write(ecodes.EV_REL, ecodes.REL_WHEEL, dy)
            if dx != 0:
                self._uinput.write(ecodes.EV_REL, ecodes.REL_HWHEEL, dx)
            self._uinput.syn()

    def _close_uinput(self) -> None:
        if self._uinput is not None:
            try:
                self._uinput.close()
            except (OSError, RuntimeError) as e:
                logger.debug(f"[CONTROLLER] Error closing mouse uinput device: {e}")
            self._uinput = None


def _parse_int_pair(s: str) -> tuple[int, int]:
    a, _, b = s.partition(",")
    return int(a), int(b)


_BTN_NAME_TO_EVDEV: dict[str, int] = {}
_BTN_NAME_TO_PYNPUT: dict[str, Button] = {}


def _build_btn_maps() -> None:
    if ecodes is not None:
        _BTN_NAME_TO_EVDEV.update(
            {
                "left": ecodes.BTN_LEFT,
                "right": ecodes.BTN_RIGHT,
                "middle": ecodes.BTN_MIDDLE,
            }
        )
    _BTN_NAME_TO_PYNPUT.update(
        {
            "left": Button.left,
            "right": Button.right,
            "middle": Button.middle,
        }
    )


_build_btn_maps()
