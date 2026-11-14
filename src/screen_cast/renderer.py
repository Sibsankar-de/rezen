import multiprocessing as mp
import queue
import subprocess
import sys
import time
from typing import Any

import cv2
import numpy as np

try:
    from pynput._util.xorg import Xlib
except ImportError:
    Xlib = None

from settings import settings
from utils.logger import get_logger
from utils.multiprocessing_fix import apply_multiprocessing_fix

apply_multiprocessing_fix()
logger = get_logger(__name__)

_GUI_NORMAL_FLAG = getattr(cv2, "WINDOW_GUI_NORMAL", 0)
_KEEPRATIO_FLAG = getattr(cv2, "WINDOW_KEEPRATIO", 0)


def _hex_to_bgr(hex_code: str) -> tuple[int, int, int]:
    clean = hex_code.lstrip("#")
    if len(clean) == 6:
        try:
            r = int(clean[0:2], 16)
            g = int(clean[2:4], 16)
            b = int(clean[4:6], 16)
            return (b, g, r)
        except ValueError:
            pass
    return (118, 230, 0)


def _draw_cursor_arrow(
    img: np.ndarray,
    origin_x: int,
    origin_y: int,
    fill_bgr: tuple[int, int, int],
    size: int = 18,
) -> None:
    h, w = img.shape[:2]
    if origin_x < 0 or origin_x >= w or origin_y < 0 or origin_y >= h:
        return

    pts = np.array(
        [
            [origin_x, origin_y],
            [origin_x, min(h - 1, origin_y + int(size * 0.9))],
            [min(w - 1, origin_x + int(size * 0.28)), min(h - 1, origin_y + int(size * 0.68))],
            [min(w - 1, origin_x + int(size * 0.55)), min(h - 1, origin_y + int(size * 1.0))],
            [min(w - 1, origin_x + int(size * 0.7)), min(h - 1, origin_y + int(size * 0.9))],
            [min(w - 1, origin_x + int(size * 0.44)), min(h - 1, origin_y + int(size * 0.58))],
            [min(w - 1, origin_x + int(size * 0.75)), min(h - 1, origin_y + int(size * 0.58))],
        ],
        dtype=np.int32,
    )
    cv2.fillPoly(img, [pts], fill_bgr)
    cv2.polylines(img, [pts], isClosed=True, color=(0, 0, 0), thickness=2, lineType=cv2.LINE_AA)


def _disable_x11_mousewheel(window: Any) -> None:
    """Recursively grab mouse buttons 4-7 on an X11 window to drop scroll events from Qt."""
    if Xlib is None:
        return
    for btn in (4, 5, 6, 7):
        try:
            window.grab_button(
                btn,
                Xlib.X.AnyModifier,
                0,  # owner_events = False -> drops event from entering Qt event queue
                0,  # event_mask = 0
                Xlib.X.GrabModeAsync,
                Xlib.X.GrabModeAsync,
                Xlib.X.NONE,
                Xlib.X.NONE,
            )
        except Exception:
            pass
    tree = getattr(window, "query_tree", None)
    if tree:
        try:
            for child in tree().children:
                _disable_x11_mousewheel(child)
        except Exception:
            pass


def _disable_mousewheel_zoom(window_name: str) -> bool:
    """Disable mouse wheel zoom on Linux/X11 by grabbing buttons 4-7 on the window hierarchy."""
    if not sys.platform.startswith("linux") or Xlib is None:
        return False
    display = _get_xlib_display()
    if display is None:
        return False
    try:
        display.sync()
        root = display.screen().root

        def _find_and_disable(w: Any) -> bool:
            wm_name = getattr(w, "get_wm_name", lambda: None)()
            if wm_name and window_name in wm_name:
                _disable_x11_mousewheel(w)
                return True
            tree = getattr(w, "query_tree", None)
            if tree:
                for child in tree().children:
                    if _find_and_disable(child):
                        return True
            return False

        found = _find_and_disable(root)
        if found:
            display.sync()
        return found
    except Exception as exc:
        logger.debug(f"Could not disable mousewheel zoom via Xlib: {exc}")
        return False


def _is_window_open(window_name: str) -> bool:
    """Check if OpenCV window is open and valid."""
    try:
        prop = cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE)
        return prop >= 0.0
    except cv2.error:
        return False
    except Exception:
        return False


_xlib_display: Any = None


def _get_xlib_display() -> Any:
    """Return a cached Xlib Display connection, reconnecting if needed."""
    global _xlib_display
    if _xlib_display is None and sys.platform.startswith("linux") and Xlib is not None:
        try:
            _xlib_display = Xlib.display.Display()
        except Exception:   
            _xlib_display = None
    return _xlib_display


def _is_window_focused(window_name: str) -> bool:
    """Check if the window titled window_name is currently focused."""
    global _xlib_display

    if sys.platform == "win32":
        try:
            import ctypes

            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return False
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                return window_name in buf.value
        except Exception:
            return False
        return False

    display = _get_xlib_display()
    if display is not None:
        try:
            display.sync()
            w = display.get_input_focus().focus
            while w:
                name = getattr(w, "get_wm_name", lambda: None)()
                if name and window_name in name:
                    return True
                tree_fn = getattr(w, "query_tree", None)
                if not tree_fn:
                    break
                p = tree_fn().parent
                if p == w or p is None:
                    break
                w = p
        except Exception:   
            try:
                display.close()
            except Exception:   
                pass
            _xlib_display = None
        return False

    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True,
            text=True,
            timeout=0.08,
            check=False,
        )
        if result.returncode == 0 and window_name in result.stdout:
            return True
    except Exception:   
        pass

    return False


def _poll_window_state(
    window_name: str,
    win_geometry: Any,
    is_focused: Any,
) -> None:
    """
    Query window content geometry and active focus state.
    Updates win_geometry[0..3] = (screen_x, screen_y, w, h) and is_focused.value.
    Defaults to is_focused=0 if unconfirmed.
    """
    try:
        img_rect = cv2.getWindowImageRect(window_name)
        if img_rect[2] > 0 and img_rect[3] > 0:
            win_geometry[0] = img_rect[0]
            win_geometry[1] = img_rect[1]
            win_geometry[2] = img_rect[2]
            win_geometry[3] = img_rect[3]
    except Exception:
        pass

    try:
        is_focused.value = int(_is_window_focused(window_name))
    except Exception:
        pass


def _render_process_entry(
    frame_queue: Any,
    stop_event: Any,
    window_name: str,
    win_geometry: Any,
    is_focused: Any,
    cursor_state: Any = None,
    source_dims: Any = None,
    pointer_color_bgr: tuple[int, int, int] | None = None,
    pointer_size: int | None = None,
) -> None:
    """
    Dedicated renderer process main body.
    Runs on the MainThread of the dedicated renderer process,
    fully complying with Qt/X11 GUI main-thread restrictions.
    """
    window_created = False
    try:
        try:
            cv2.startWindowThread()
        except Exception:
            pass

        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL | _KEEPRATIO_FLAG | _GUI_NORMAL_FLAG)
        cv2.resizeWindow(window_name, 960, 540)
        cv2.setMouseCallback(window_name, lambda *args: None)
        window_created = True

        placeholder = np.zeros((540, 960, 3), dtype=np.uint8)
        cv2.putText(
            placeholder,
            "Rezen Screen Share",
            (300, 240),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            placeholder,
            "Connected - Waiting for video stream...",
            (240, 300),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (180, 180, 180),
            1,
            cv2.LINE_AA,
        )
        cv2.imshow(window_name, placeholder)
        for _ in range(5):
            cv2.waitKey(20)
        _poll_window_state(window_name, win_geometry, is_focused)
        wheel_disabled = _disable_mousewheel_zoom(window_name)
    except Exception as exc:
        logger.warning(f"Error creating window in renderer process: {exc}")

    start_time = time.time()
    last_poll_time = time.monotonic()
    invisible_count = 0
    while not stop_event.is_set():
        if not wheel_disabled and time.time() - start_time < 3.0:
            wheel_disabled = _disable_mousewheel_zoom(window_name)
        try:
            frame = frame_queue.get(timeout=0.03)
            if frame is None:
                stop_event.set()
                break

            if cursor_state is not None:
                has_host = cursor_state[2] == 1
                has_remote = cursor_state[5] == 1
                if has_host or has_remote:
                    if not frame.flags.writeable:
                        frame = frame.copy()
                    h_w = source_dims[0] if (source_dims is not None and source_dims[0] > 0) else frame.shape[1]
                    h_h = source_dims[1] if (source_dims is not None and source_dims[1] > 0) else frame.shape[0]
                    scale_x = frame.shape[1] / h_w
                    scale_y = frame.shape[0] / h_h
                    p_size = pointer_size or settings.REMOTE_POINTER_SIZE

                    if has_host:
                        hx = int(round(cursor_state[0] * scale_x))
                        hy = int(round(cursor_state[1] * scale_y))
                        _draw_cursor_arrow(frame, hx, hy, (255, 255, 255), size=p_size)

                    if has_remote:
                        rx = int(round(cursor_state[3] * scale_x))
                        ry = int(round(cursor_state[4] * scale_y))
                        col = pointer_color_bgr or (118, 230, 0)
                        _draw_cursor_arrow(frame, rx, ry, col, size=p_size)

            cv2.imshow(window_name, frame)
            cv2.waitKey(1)
        except queue.Empty:
            cv2.waitKey(20)
        except Exception as exc:
            logger.warning(f"Error displaying frame in renderer process: {exc}")

        now = time.monotonic()
        if now - last_poll_time >= 0.05:
            last_poll_time = now
            _poll_window_state(window_name, win_geometry, is_focused)

        if time.time() - start_time > 3.0:
            if not _is_window_open(window_name):
                invisible_count += 1
                if invisible_count >= 20:
                    logger.info("Renderer window closed by user.")
                    stop_event.set()
                    break
            else:
                invisible_count = 0

    try:
        if window_created:
            cv2.destroyWindow(window_name)
            for _ in range(3):
                cv2.waitKey(10)
    except Exception:
        pass


class ScreenRenderer:
    """Render the frames in a dedicated process."""

    def __init__(self):
        self._closed = True
        self._window_name = settings.SCREEN_RENDER_WINDOW_NAME
        self._queue: Any = None
        self._stop_event: Any = None
        self._process: Any = None
        self._win_geometry: Any = None
        self._is_focused: Any = None
        self._cursor_state: Any = None
        self._source_dims: Any = None
        self._source_size = (
            settings.SCREEN_CAPTURE_MAX_WIDTH,
            settings.SCREEN_CAPTURE_MAX_HEIGHT,
        )
        self._has_host_resolution = False

    def set_host_resolution(self, width: int, height: int) -> None:
        """Set the authoritative host screen dimensions for coordinate mapping."""
        if width > 0 and height > 0:
            self._source_size = (int(width), int(height))
            self._has_host_resolution = True
            if self._source_dims is not None:
                self._source_dims[0] = int(width)
                self._source_dims[1] = int(height)
            logger.info(f"ScreenRenderer host screen resolution set to {width}x{height}.")

    def set_host_cursor(self, x: int, y: int, visible: bool = True) -> None:
        """Update host cursor position for overlay in renderer."""
        if self._cursor_state is not None:
            self._cursor_state[0] = int(x)
            self._cursor_state[1] = int(y)
            self._cursor_state[2] = 1 if visible else 0

    def set_remote_pointer(self, x: int, y: int, visible: bool = True) -> None:
        """Update remote pointer position for local renderer."""
        if self._cursor_state is not None:
            self._cursor_state[3] = int(x)
            self._cursor_state[4] = int(y)
            self._cursor_state[5] = 1 if visible else 0

    @property
    def isClosed(self) -> bool:
        if self._closed:
            return True
        if self._process is not None and not self._process.is_alive():
            self._closed = True
            return True
        if self._stop_event is not None and self._stop_event.is_set():
            self._closed = True
            return True
        return False

    @property
    def window_geometry(self) -> tuple[int, int, int, int]:
        """(screen_x, screen_y, content_w, content_h) of the CV2 window content area."""
        if self._win_geometry is None:
            return (0, 0, 960, 540)
        return (
            self._win_geometry[0],
            self._win_geometry[1],
            self._win_geometry[2],
            self._win_geometry[3],
        )

    @property
    def is_focused(self) -> bool:
        if self._is_focused is None:
            return False
        return bool(self._is_focused.value)

    @property
    def source_size(self) -> tuple[int, int]:
        """(width, height) of the video frames being rendered."""
        return self._source_size

    def start(self) -> None:
        """Start the renderer process and display the window immediately."""
        if not self._closed:
            return

        self._closed = False
        apply_multiprocessing_fix()
        ctx = mp.get_context("spawn")
        self._queue = ctx.Queue(maxsize=30)
        self._stop_event = ctx.Event()
        self._win_geometry = ctx.Array("i", [0, 0, 960, 540])
        self._is_focused = ctx.Value("b", 0)
        self._cursor_state = ctx.Array("i", [-1, -1, 0, -1, -1, 0])
        self._source_dims = ctx.Array("i", [self._source_size[0], self._source_size[1]])
        color_bgr = _hex_to_bgr(settings.REMOTE_POINTER_COLOR)
        p_size = settings.REMOTE_POINTER_SIZE

        self._process = ctx.Process(
            target=_render_process_entry,
            args=(
                self._queue,
                self._stop_event,
                self._window_name,
                self._win_geometry,
                self._is_focused,
                self._cursor_state,
                self._source_dims,
                color_bgr,
                p_size,
            ),
            name="ScreenRendererProcess",
            daemon=True,
        )
        self._process.start()
        logger.info(f"ScreenRenderer process started (PID: {self._process.pid}).")

    def display(self, frame: np.ndarray) -> bool:
        """Queue frame for rendering."""
        if self.isClosed or self._queue is None:
            return False

        if not self._has_host_resolution and frame is not None and getattr(frame, "ndim", 0) >= 2:
            self._source_size = (int(frame.shape[1]), int(frame.shape[0]))

        if self._queue.full():
            try:
                self._queue.get_nowait()
            except Exception:
                pass

        try:
            self._queue.put_nowait(frame)
            return True
        except Exception:
            return False

    def close(self) -> None:
        """Signal the render process to stop and clean up."""
        if self._closed and self._process is None:
            return

        self._closed = True
        if self._stop_event is not None:
            self._stop_event.set()

        if self._queue is not None:
            try:
                self._queue.put_nowait(None)
            except Exception:
                pass

        if self._process is not None:
            if self._process.is_alive():
                self._process.join(timeout=1.0)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=0.5)
            self._process = None

        if self._queue is not None:
            try:
                self._queue.close()
            except Exception:
                pass
            self._queue = None

        self._stop_event = None
        self._win_geometry = None
        self._is_focused = None
        logger.info("ScreenRenderer closed cleanly.")

    def _is_window_open(self) -> bool:
        return _is_window_open(self._window_name)
