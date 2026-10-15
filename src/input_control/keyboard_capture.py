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

from pynput.keyboard import Key, KeyCode, Listener

from input_control.normalizer import KeyNormalizer
from models.input import InputObject, InputType
from utils.logger import get_logger

logger = get_logger(__name__)


class KeyboardCapture:
    """Capture keyboard events using evdev (preferred on Linux/Wayland) or pynput (fallback)."""

    def __init__(self):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._enqueue: Callable[[InputObject], Any] | None = None
        self._listner: Listener | None = None
        self._evdev_devices: list[Any] = []
        self._evdev_tasks: list[asyncio.Task] = []
        self._pressed_keys: set[str] = set()
        self._backend: str | None = None

    async def start(self, enqueue: Callable[[InputObject], Any]) -> None:
        """Start the keyboard listener using evdev if available, else pynput."""
        if self._is_running():
            logger.info("KeyboardCapture is already running.")
            return

        self._loop = asyncio.get_running_loop()
        self._enqueue = enqueue
        session_type = self._log_environment()

        if self._can_use_evdev() and self._start_evdev():
            return

        self._start_pynput(session_type)

    async def stop(self) -> None:
        """Stop keyboard capturing (evdev or pynput)."""
        if self._evdev_tasks:
            await self._stop_evdev()

        if self._listner is not None:
            await self._stop_pynput()

        self._pressed_keys.clear()

    def _is_running(self) -> bool:
        """Check if any capture backend is currently active."""
        pynput_active = self._listner is not None and self._listner.is_alive()
        return pynput_active or bool(self._evdev_tasks)

    def _log_environment(self) -> str:
        """Log runtime platform and session diagnostics."""
        session_type = os.environ.get("XDG_SESSION_TYPE", "unknown")
        display = os.environ.get("DISPLAY", "")
        wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
        logger.info(
            f"Initializing KeyboardCapture (OS: {sys.platform}, session: {session_type}, "
            f"DISPLAY: '{display}', WAYLAND_DISPLAY: '{wayland_display}')"
        )
        return session_type

    @staticmethod
    def _can_use_evdev() -> bool:
        """Check if platform and dependencies support evdev."""
        return sys.platform.startswith("linux") and evdev is not None

    def _start_evdev(self) -> bool:
        """Discover keyboards and start evdev async read tasks. Returns True on success."""
        keyboards = self._discover_evdev_keyboards()
        if not keyboards:
            return False

        self._backend = "evdev"
        self._evdev_devices = keyboards
        dev_names = [f"{d.name} ({d.path})" for d in keyboards]
        logger.info(
            f"[CAPTURE] Using evdev backend with {len(keyboards)} keyboard(s): {dev_names}"
        )
        self._evdev_tasks = [
            asyncio.create_task(self._evdev_read_device(d)) for d in keyboards
        ]
        return True

    def _discover_evdev_keyboards(self) -> list[Any]:
        """Find readable Linux evdev keyboard devices."""
        if evdev is None or ecodes is None:
            return []

        keyboards = []
        permission_denied = False

        for path in sorted(glob.glob("/dev/input/event*")):
            try:
                dev = evdev.InputDevice(path)
                if self._is_keyboard_device(dev):
                    keyboards.append(dev)
                else:
                    self._close_device(dev)
            except PermissionError:
                permission_denied = True
            except OSError:
                continue

        if permission_denied and not keyboards:
            logger.warning(
                "[CAPTURE] Permission denied accessing /dev/input/event*. "
                "To enable global Wayland keyboard capture via evdev, run:\n"
                "    sudo usermod -aG input $USER\n"
                "(then log out and back in to apply group membership)."
            )

        return keyboards

    @staticmethod
    def _is_keyboard_device(dev: Any) -> bool:
        """Verify device is an actual hardware keyboard and not a virtual uinput device."""
        if ecodes is None:
            return False
        name = dev.name.lower()
        if "rezen" in name or "uinput" in name:
            return False
        caps = dev.capabilities()
        if ecodes.EV_KEY not in caps:
            return False
        keys = caps[ecodes.EV_KEY]
        return ecodes.KEY_A in keys and ecodes.KEY_ENTER in keys

    async def _evdev_read_device(self, dev: Any) -> None:
        """Read events from an evdev device asynchronously."""
        try:
            async for event in dev.async_read_loop():
                if ecodes and event.type == ecodes.EV_KEY:
                    if event.value in (1, 2):  # 1: press, 2: hold/repeat
                        self._handle_key_press(
                            KeyNormalizer.normalize_evdev_key(event.code),
                            source=f"evdev:{event.code}",
                        )
                    elif event.value == 0:  # 0: release
                        self._handle_key_release(
                            KeyNormalizer.normalize_evdev_key(event.code),
                            source=f"evdev:{event.code}",
                        )
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception(
                f"[CAPTURE] [evdev] Error reading from {dev.name} ({dev.path})"
            )
        finally:
            self._close_device(dev)

    async def _stop_evdev(self) -> None:
        """Cancel evdev background tasks and close device handles."""
        logger.info("Stopping evdev keyboard capture tasks...")
        for task in self._evdev_tasks:
            task.cancel()
        await asyncio.gather(*self._evdev_tasks, return_exceptions=True)
        self._evdev_tasks.clear()

        for dev in self._evdev_devices:
            self._close_device(dev)
        self._evdev_devices.clear()
        logger.info("evdev keyboard capture stopped.")

    @staticmethod
    def _close_device(dev: Any) -> None:
        """Safely close an evdev device descriptor."""
        try:
            dev.close()
        except (OSError, RuntimeError) as e:
            logger.debug(
                f"[CAPTURE] Error closing device {getattr(dev, 'path', dev)}: {e}"
            )

    def _start_pynput(self, session_type: str) -> None:
        """Start the pynput keyboard listener."""
        self._backend = "pynput"
        if session_type.lower() == "wayland":
            logger.warning(
                "Wayland session detected and evdev capture unavailable. Falling back to pynput: "
                "keystrokes outside Xwayland windows cannot be captured globally."
            )

        self._listner = Listener(
            on_press=self._on_pynput_press, on_release=self._on_pynput_release
        )
        self._listner.start()
        logger.info(
            f"KeyboardCapture listener started (backend: pynput/{self._listner.__class__.__name__}, "
            f"is_alive: {self._listner.is_alive()})."
        )

    def _on_pynput_press(self, key: Key | KeyCode | None) -> None:
        """Handle pynput key press event."""
        self._handle_key_press(
            KeyNormalizer.normalize_key(key), source=f"pynput:{key!r}"
        )

    def _on_pynput_release(self, key: Key | KeyCode | None) -> None:
        """Handle pynput key release event."""
        self._handle_key_release(
            KeyNormalizer.normalize_key(key), source=f"pynput:{key!r}"
        )

    async def _stop_pynput(self) -> None:
        """Stop and join pynput listener thread."""
        if self._listner is None:
            return

        logger.info("Stopping pynput KeyboardCapture listener...")
        self._listner.stop()
        try:
            await asyncio.to_thread(self._listner.join, 0.5)
        except Exception:  # noqa: BLE001
            logger.debug("KeyboardCapture listener thread join timed out or failed.")
        self._listner = None
        logger.info("pynput KeyboardCapture listener stopped cleanly.")

    def _handle_key_press(self, normalized_key: str | None, source: str) -> None:
        """Register a key press, update active keys, and dispatch event."""
        try:
            if not normalized_key:
                logger.debug(f"[CAPTURE] Unmapped key press from {source}")
                return

            self._pressed_keys.add(normalized_key)
            logger.info(
                f"[CAPTURE] [{self._backend}] Key pressed ({source}) -> norm='{normalized_key}' | "
                f"Active: {self._pressed_keys}"
            )
            self._dispatch_event()
        except Exception:
            logger.exception(f"Error handling key press for {source}")

    def _handle_key_release(self, normalized_key: str | None, source: str) -> None:
        """Register a key release and update active keys."""
        try:
            if not normalized_key:
                logger.debug(f"[CAPTURE] Unmapped key release from {source}")
                return

            self._pressed_keys.discard(normalized_key)
            logger.info(
                f"[CAPTURE] [{self._backend}] Key released ({source}) -> norm='{normalized_key}' | "
                f"Active: {self._pressed_keys}"
            )
        except Exception:
            logger.exception(f"Error handling key release for {source}")

    def _dispatch_event(self) -> None:
        """Send current pressed keys snapshot to the consumer callback."""
        if self._loop is None or self._loop.is_closed() or self._enqueue is None:
            logger.warning(
                "Event loop is closed or unassigned; dropping key press event."
            )
            return

        event = InputObject(type=InputType.KEYBOARD, data=set(self._pressed_keys))
        self._loop.call_soon_threadsafe(self._enqueue, event)


