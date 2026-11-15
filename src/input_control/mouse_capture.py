import asyncio
import glob
import os
import sys
from collections.abc import Callable
from typing import Any

try:
    import evdev
    from evdev import ecodes
except ImportError:
    evdev = None
    ecodes = None

from pynput.mouse import Button, Listener

from input_control.window_context import WindowContext
from models.input import InputObject, InputType
from settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class MouseCapture:
    """Capture mouse events using evdev (preferred on Linux/Wayland) or pynput (fallback)."""

    def __init__(self):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._enqueue: Callable[[InputObject], Any] | None = None
        self._listener: Listener | None = None
        self._evdev_devices: list[Any] = []
        self._evdev_tasks: list[asyncio.Task] = []
        self._renderer_task: asyncio.Task | None = None
        self._backend: str | None = None
        self._renderer: WindowContext | None = None

    async def start(
        self,
        enqueue: Callable[[InputObject], Any],
        renderer: WindowContext | None = None,
    ) -> None:
        """Start mouse capture using renderer callback queue (preferred), pynput, or evdev (fallback)."""
        if self._is_running():
            logger.info("MouseCapture is already running.")
            return

        self._loop = asyncio.get_running_loop()
        self._enqueue = enqueue
        self._renderer = renderer

        if (
            self._renderer is not None
            and getattr(self._renderer, "mouse_event_queue", None) is not None
        ):
            self._backend = "renderer_window"
            self._renderer_task = asyncio.create_task(self._renderer_read_loop())
            logger.info("[CAPTURE] MouseCapture using dedicated renderer window callback queue.")
            return

        session_type = self._log_environment()

        try:
            self._start_pynput(session_type)
            return
        except Exception as exc:
            logger.warning(
                f"Could not start pynput mouse listener ({exc}); falling back to evdev if available."
            )

        if self._can_use_evdev() and self._start_evdev():
            return

        logger.error(
            "Failed to start mouse capture: neither pynput nor evdev could be initialized."
        )

    async def stop(self) -> None:
        """Stop mouse capture."""
        if self._renderer_task is not None:
            self._renderer_task.cancel()
            await asyncio.gather(self._renderer_task, return_exceptions=True)
            self._renderer_task = None

        if self._evdev_tasks:
            await self._stop_evdev()

        if self._listener is not None:
            await self._stop_pynput()

    def _is_running(self) -> bool:
        renderer_active = self._renderer_task is not None and not self._renderer_task.done()
        pynput_active = self._listener is not None and self._listener.is_alive()
        return renderer_active or pynput_active or bool(self._evdev_tasks)

    async def _renderer_read_loop(self) -> None:
        """Read mouse events from the OpenCV renderer window queue asynchronously."""
        q = getattr(self._renderer, "mouse_event_queue", None)
        if q is None:
            return

        loop = self._loop or asyncio.get_running_loop()
        try:
            while True:
                event_tuple = await loop.run_in_executor(None, self._poll_renderer_queue, q)
                if event_tuple is None:
                    continue
                # Coalesce consecutive move events to eliminate queue latency
                while not q.empty():
                    try:
                        next_tuple = q.get_nowait()
                        if next_tuple[0] == "move" and event_tuple[0] == "move":
                            event_tuple = next_tuple
                        else:
                            self._process_renderer_event(event_tuple)
                            event_tuple = next_tuple
                    except Exception:
                        break
                self._process_renderer_event(event_tuple)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("[CAPTURE] Error reading renderer mouse event queue")

    @staticmethod
    def _poll_renderer_queue(q: Any) -> Any:
        try:
            return q.get(timeout=0.1)
        except Exception:
            return None

    def _process_renderer_event(self, event_tuple: tuple[Any, ...]) -> None:
        if self._renderer is None or self._enqueue is None:
            return

        kind = event_tuple[0]
        if hasattr(self._renderer, "source_size"):
            host_w, host_h = self._renderer.source_size
        else:
            host_w = settings.SCREEN_CAPTURE_MAX_WIDTH
            host_h = settings.SCREEN_CAPTURE_MAX_HEIGHT

        if kind == "move":
            if len(event_tuple) >= 7:
                _, cx, cy, fw, fh, nx, ny = event_tuple[:7]
            else:
                _, cx, cy, fw, fh = event_tuple[:5]
                nx = cx / fw if fw > 0 else 0.0
                ny = cy / fh if fh > 0 else 0.0

            if fw <= 0 or fh <= 0:
                return
            scale_x = host_w / fw
            scale_y = host_h / fh
            hx = max(0, min(host_w - 1, round(cx * scale_x)))
            hy = max(0, min(host_h - 1, round(cy * scale_y)))
            self._enqueue_now(f"move_abs:{hx},{hy}:{nx:.6f},{ny:.6f}")

        elif kind == "click":
            if len(event_tuple) >= 8:
                _, btn, state, cx, cy, fw, fh, nx, ny = event_tuple[:9]
            else:
                _, btn, state, cx, cy, fw, fh = event_tuple[:7]
                nx = cx / fw if fw > 0 else 0.0
                ny = cy / fh if fh > 0 else 0.0

            if fw <= 0 or fh <= 0:
                return
            scale_x = host_w / fw
            scale_y = host_h / fh
            hx = max(0, min(host_w - 1, round(cx * scale_x)))
            hy = max(0, min(host_h - 1, round(cy * scale_y)))
            self._enqueue_now(f"move_abs:{hx},{hy}:{nx:.6f},{ny:.6f}")
            self._enqueue_now(f"click:{btn}:{state}:{hx},{hy}:{nx:.6f},{ny:.6f}")

        elif kind == "scroll":
            _, dx, dy, cx, cy, fw, fh = event_tuple
            self._enqueue_now(f"scroll:{dx},{dy}")

    def _enqueue_now(self, encoded: str) -> None:
        if self._loop is None or self._loop.is_closed() or self._enqueue is None:
            return
        event = InputObject(type=InputType.MOUSE, data={encoded})
        self._loop.call_soon_threadsafe(self._enqueue, event)

    def _log_environment(self) -> str:
        session_type = os.environ.get("XDG_SESSION_TYPE", "unknown")
        display = os.environ.get("DISPLAY", "")
        wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
        logger.info(
            f"Initializing MouseCapture (OS: {sys.platform}, session: {session_type}, "
            f"DISPLAY: '{display}', WAYLAND_DISPLAY: '{wayland_display}')"
        )
        return session_type

    @staticmethod
    def _can_use_evdev() -> bool:
        return sys.platform.startswith("linux") and evdev is not None

    def _start_evdev(self) -> bool:
        """Discover mouse devices and start evdev async read tasks."""
        mice = self._discover_evdev_mice()
        if not mice:
            return False

        self._backend = "evdev"
        self._evdev_devices = mice
        dev_names = [f"{d.name} ({d.path})" for d in mice]
        logger.info(
            f"[CAPTURE] MouseCapture using evdev with {len(mice)} device(s): {dev_names}"
        )
        self._evdev_tasks = [
            asyncio.create_task(self._evdev_read_device(d)) for d in mice
        ]
        return True

    def _discover_evdev_mice(self) -> list[Any]:
        """Find readable Linux evdev mouse/pointer devices."""
        if evdev is None or ecodes is None:
            return []

        mice = []
        permission_denied = False

        for path in sorted(glob.glob("/dev/input/event*")):
            try:
                dev = evdev.InputDevice(path)
                if self._is_mouse_device(dev):
                    mice.append(dev)
                else:
                    self._close_device(dev)
            except PermissionError:
                permission_denied = True
            except OSError:
                continue

        if permission_denied and not mice:
            logger.warning(
                "[CAPTURE] Permission denied accessing /dev/input/event*. "
                "To enable global mouse capture via evdev, run:\n"
                "    sudo usermod -aG input $USER\n"
                "(then log out and back in to apply group membership)."
            )

        return mice

    @staticmethod
    def _is_mouse_device(dev: Any) -> bool:
        """Verify device is a hardware mouse/pointer, not a rezen virtual device."""
        if ecodes is None:
            return False
        name = dev.name.lower()
        if "rezen" in name or "uinput" in name:
            return False
        caps = dev.capabilities()
        if ecodes.EV_REL not in caps:
            return False
        rel_codes = caps[ecodes.EV_REL]
        return ecodes.REL_X in rel_codes and ecodes.REL_Y in rel_codes

    async def _evdev_read_device(self, dev: Any) -> None:
        """Read mouse events from an evdev device asynchronously."""
        rel_x = 0
        rel_y = 0
        try:
            async for event in dev.async_read_loop():
                if ecodes is None:
                    continue

                if event.type == ecodes.EV_REL:
                    if event.code == ecodes.REL_X:
                        rel_x += event.value
                    elif event.code == ecodes.REL_Y:
                        rel_y += event.value
                    elif event.code == ecodes.REL_WHEEL:
                        self._dispatch(f"scroll:0,{event.value}")
                    elif event.code == ecodes.REL_HWHEEL:
                        self._dispatch(f"scroll:{event.value},0")

                elif event.type == ecodes.EV_SYN:
                    if rel_x != 0 or rel_y != 0:
                        self._dispatch(f"move:{rel_x},{rel_y}")
                        rel_x = 0
                        rel_y = 0

                elif event.type == ecodes.EV_KEY:
                    btn = _EVDEV_BTN_MAP.get(event.code)
                    if btn is not None:
                        pressed = 1 if event.value == 1 else 0
                        self._dispatch(f"click:{btn}:{pressed}")

        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception(
                f"[CAPTURE] [evdev] Error reading from {dev.name} ({dev.path})"
            )
        finally:
            self._close_device(dev)

    async def _stop_evdev(self) -> None:
        logger.info("Stopping evdev mouse capture tasks...")
        for task in self._evdev_tasks:
            task.cancel()
        await asyncio.gather(*self._evdev_tasks, return_exceptions=True)
        self._evdev_tasks.clear()

        for dev in self._evdev_devices:
            self._close_device(dev)
        self._evdev_devices.clear()
        logger.info("evdev mouse capture stopped.")

    @staticmethod
    def _close_device(dev: Any) -> None:
        try:
            dev.close()
        except (OSError, RuntimeError) as e:
            logger.debug(
                f"[CAPTURE] Error closing device {getattr(dev, 'path', dev)}: {e}"
            )

    def _start_pynput(self, session_type: str) -> None:
        """Start the pynput mouse listener."""
        self._backend = "pynput"
        if session_type.lower() == "wayland":
            logger.warning(
                "Wayland session detected and evdev mouse capture unavailable. "
                "Falling back to pynput: mouse events outside Xwayland windows "
                "cannot be captured globally."
            )

        self._listener = Listener(
            on_move=self._on_pynput_move,
            on_click=self._on_pynput_click,
            on_scroll=self._on_pynput_scroll,
        )
        self._listener.start()
        logger.info(
            f"MouseCapture listener started (backend: pynput, is_alive: {self._listener.is_alive()})."
        )

    def _on_pynput_move(self, x: int, y: int) -> None:
        self._dispatch(f"move_abs:{x},{y}")

    def _on_pynput_click(self, x: int, y: int, button: Button, pressed: bool) -> None:
        if self._renderer is not None:
            if not self._renderer.is_focused:
                return
            win_x, win_y, win_w, win_h = self._renderer.window_geometry
            if win_w > 0 and win_h > 0:
                rel_x = x - win_x
                rel_y = y - win_y
                if rel_x < 0 or rel_x >= win_w or rel_y < 0 or rel_y >= win_h:
                    return
                self._dispatch(f"move_abs:{x},{y}")
        btn_name = _PYNPUT_BTN_NAME.get(button, button.name)
        self._dispatch(f"click:{btn_name}:{1 if pressed else 0}")

    def _on_pynput_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        if self._renderer is not None:
            if not self._renderer.is_focused:
                return
            win_x, win_y, win_w, win_h = self._renderer.window_geometry
            if win_w > 0 and win_h > 0:
                rel_x = x - win_x
                rel_y = y - win_y
                if rel_x < 0 or rel_x >= win_w or rel_y < 0 or rel_y >= win_h:
                    return
        self._dispatch(f"scroll:{dx},{dy}")

    async def _stop_pynput(self) -> None:
        if self._listener is None:
            return
        logger.info("Stopping pynput MouseCapture listener...")
        self._listener.stop()
        try:
            await asyncio.to_thread(self._listener.join, 0.5)
        except Exception:
            logger.debug("MouseCapture listener thread join timed out or failed.")
        self._listener = None
        logger.info("pynput MouseCapture listener stopped.")

    def _dispatch(self, encoded: str) -> None:
        """Gate on window focus, translate coordinates, then enqueue the event."""
        if self._loop is None or self._loop.is_closed() or self._enqueue is None:
            return

        if self._renderer is not None and not self._renderer.is_focused:
            return

        translated = self._translate(encoded)
        if translated is None:
            return

        event = InputObject(type=InputType.MOUSE, data={translated})
        self._loop.call_soon_threadsafe(self._enqueue, event)

    def _translate(self, encoded: str) -> str | None:
        """
        Remap mouse coordinates from viewer window space to host screen space.
        Returns None when the event should be dropped (e.g. zero-delta after scaling).
        """
        if self._renderer is None:
            return encoded

        win_x, win_y, win_w, win_h = self._renderer.window_geometry
        if hasattr(self._renderer, "source_size"):
            host_w, host_h = self._renderer.source_size
        else:
            host_w = settings.SCREEN_CAPTURE_MAX_WIDTH
            host_h = settings.SCREEN_CAPTURE_MAX_HEIGHT

        if win_w <= 0 or win_h <= 0:
            return encoded

        kind, _, rest = encoded.partition(":")

        if kind == "move_abs":
            screen_x, screen_y = _parse_int_pair(rest)
            rel_x = screen_x - win_x
            rel_y = screen_y - win_y
            if rel_x < 0 or rel_x >= win_w or rel_y < 0 or rel_y >= win_h:
                return None
            scale_x = host_w / win_w
            scale_y = host_h / win_h
            host_x = max(0, min(host_w - 1, round(rel_x * scale_x)))
            host_y = max(0, min(host_h - 1, round(rel_y * scale_y)))
            if rel_x >= win_w - 1:
                host_x = host_w - 1
            if rel_y >= win_h - 1:
                host_y = host_h - 1
            return f"move_abs:{host_x},{host_y}"

        if kind == "move":
            dx, dy = _parse_int_pair(rest)
            scale_x = host_w / win_w
            scale_y = host_h / win_h
            sdx = round(dx * scale_x)
            sdy = round(dy * scale_y)
            if dx != 0 and sdx == 0:
                sdx = 1 if dx > 0 else -1
            if dy != 0 and sdy == 0:
                sdy = 1 if dy > 0 else -1
            if sdx == 0 and sdy == 0:
                return None
            return f"move:{sdx},{sdy}"

        return encoded


def _parse_int_pair(s: str) -> tuple[int, int]:
    a, _, b = s.partition(",")
    return int(a), int(b)


_EVDEV_BTN_MAP: dict[int, str] = {}
_PYNPUT_BTN_NAME: dict[Button, str] = {}


def _build_btn_maps() -> None:
    if ecodes is not None:
        _EVDEV_BTN_MAP.update(
            {
                ecodes.BTN_LEFT: "left",
                ecodes.BTN_RIGHT: "right",
                ecodes.BTN_MIDDLE: "middle",
            }
        )
    _PYNPUT_BTN_NAME.update(
        {
            Button.left: "left",
            Button.right: "right",
            Button.middle: "middle",
        }
    )


_build_btn_maps()
