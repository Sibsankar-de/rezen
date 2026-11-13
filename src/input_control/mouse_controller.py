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
        self._last_x: int | None = None
        self._last_y: int | None = None
        self._last_time: float = 0.0
        self._has_abs = False
        max_w, max_h = self._get_screen_bounds()
        self._screen_max_x = max(1, max_w - 1)
        self._screen_max_y = max(1, max_h - 1)

        self._init_backend(session_type)

    @staticmethod
    def _get_screen_bounds() -> tuple[int, int]:
        try:
            from screen_cast.capture import get_system_screen_size

            return get_system_screen_size()
        except Exception:
            return (1920, 1080)

    def set_screen_size(self, width: int, height: int) -> None:
        """Update maximum screen coordinate bounds for absolute pointer injection."""
        if width > 0 and height > 0:
            self._screen_max_x = max(1, width - 1)
            self._screen_max_y = max(1, height - 1)

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
        except Exception as exc:
            logger.warning(
                f"[CONTROLLER] Cannot initialize pynput mouse controller ({exc}). "
                "Falling back to evdev UInput if available."
            )

        if sys.platform.startswith("linux") and evdev is not None:
            self._init_evdev()

        if self._uinput is not None:
            self._backend = "evdev"
        elif self._mouse_controller is not None:
            self._backend = "pynput"
        else:
            self._backend = "none"

    def _init_evdev(self) -> bool:
        """Attempt to initialize an evdev UInput virtual mouse device."""
        if ecodes is None:
            return False

        _UInputError: type[Exception] = getattr(evdev, "UInputError", None) or type(
            "_UInputError", (Exception,), {}
        )

        events: dict[int, Any] = {
            ecodes.EV_ABS: [
                (
                    ecodes.ABS_X,
                    evdev.AbsInfo(
                        value=0,
                        min=0,
                        max=self._screen_max_x,
                        fuzz=0,
                        flat=0,
                        resolution=1,
                    ),
                ),
                (
                    ecodes.ABS_Y,
                    evdev.AbsInfo(
                        value=0,
                        min=0,
                        max=self._screen_max_y,
                        fuzz=0,
                        flat=0,
                        resolution=1,
                    ),
                ),
            ],
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
        props = (
            [ecodes.INPUT_PROP_POINTER] if hasattr(ecodes, "INPUT_PROP_POINTER") else []
        )

        try:
            self._uinput = evdev.UInput(
                events=events,
                input_props=props,
                name="rezen-virtual-mouse",
            )
            self._has_abs = True
            logger.info(
                f"[CONTROLLER] Successfully initialized evdev absolute pointer device ({self._screen_max_x + 1}x{self._screen_max_y + 1})."
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
        if self._uinput is not None and ecodes is not None:
            self._uinput.write(ecodes.EV_REL, ecodes.REL_X, dx)
            self._uinput.write(ecodes.EV_REL, ecodes.REL_Y, dy)
            self._uinput.syn()
        elif self._mouse_controller is not None:
            try:
                self._mouse_controller.move(dx, dy)
            except Exception:
                pass

    def _do_move_abs(self, x: int, y: int) -> None:
        logger.debug(f"[CONTROLLER] Mouse move abs ({x}, {y}) via {self._backend}")
        if self._uinput is not None and ecodes is not None:
            has_abs = getattr(self, "_has_abs", False)
            if not has_abs:
                caps = getattr(self._uinput, "capabilities", dict)()
                has_abs = ecodes.EV_ABS in caps

            if has_abs:
                clamped_x = max(0, min(self._screen_max_x, x))
                clamped_y = max(0, min(self._screen_max_y, y))
                self._uinput.write(ecodes.EV_ABS, ecodes.ABS_X, clamped_x)
                self._uinput.write(ecodes.EV_ABS, ecodes.ABS_Y, clamped_y)
                self._uinput.syn()
                return

            now = time.monotonic()
            if (
                self._last_x is not None
                and self._last_y is not None
                and (now - self._last_time < 0.25)
            ):
                dx = x - self._last_x
                dy = y - self._last_y
                if dx != 0 or dy != 0:
                    self._uinput.write(ecodes.EV_REL, ecodes.REL_X, dx)
                    self._uinput.write(ecodes.EV_REL, ecodes.REL_Y, dy)
                    self._uinput.syn()
            self._last_x = x
            self._last_y = y
            self._last_time = now
            return

        if self._mouse_controller is not None:
            try:
                self._mouse_controller.position = (x, y)
            except Exception:
                pass

    def _do_click(self, btn_name: str, pressed: bool) -> None:
        logger.debug(
            f"[CONTROLLER] Mouse {'press' if pressed else 'release'} {btn_name!r} via {self._backend}"
        )
        if self._uinput is not None and ecodes is not None:
            code = _BTN_NAME_TO_EVDEV.get(btn_name)
            if code is not None:
                self._uinput.write(ecodes.EV_KEY, code, 1 if pressed else 0)
                self._uinput.syn()
        elif self._mouse_controller is not None:
            button = _BTN_NAME_TO_PYNPUT.get(btn_name)
            if button is not None:
                try:
                    if pressed:
                        self._mouse_controller.press(button)
                    else:
                        self._mouse_controller.release(button)
                except Exception:
                    pass

    def _do_scroll(self, dx: int, dy: int) -> None:
        logger.debug(f"[CONTROLLER] Mouse scroll ({dx}, {dy}) via {self._backend}")
        if self._uinput is not None and ecodes is not None:
            if dy != 0:
                self._uinput.write(ecodes.EV_REL, ecodes.REL_WHEEL, dy)
            if dx != 0:
                self._uinput.write(ecodes.EV_REL, ecodes.REL_HWHEEL, dx)
            self._uinput.syn()
        elif self._mouse_controller is not None:
            try:
                self._mouse_controller.scroll(dx, dy)
            except Exception:
                pass

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
