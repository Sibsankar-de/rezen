import queue
import sys
import threading
import time

from settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


def _build_cursor_shape_rects(size: int) -> list[tuple[int, int, int, int]]:
    scale = max(1.0, size / 24.0)
    base_rects = [
        (0, 0, 2, 2),
        (0, 2, 4, 2),
        (0, 4, 6, 2),
        (0, 6, 8, 2),
        (0, 8, 10, 2),
        (0, 10, 12, 2),
        (0, 12, 14, 2),
        (0, 14, 16, 2),
        (0, 16, 8, 2),
        (0, 18, 5, 2),
        (4, 18, 4, 4),
        (6, 20, 4, 4),
    ]
    if scale == 1.0:
        return base_rects

    return [
        (
            round(x * scale),
            round(y * scale),
            max(1, round(w * scale)),
            max(1, round(h * scale)),
        )
        for x, y, w, h in base_rects
    ]


def _overlay_thread_entry(
    cmd_queue: queue.Queue,
    stop_event: threading.Event,
    color_hex: str,
    size: int,
) -> None:
    try:
        import tkinter as tk
    except ImportError:
        logger.warning("Tkinter unavailable; pointer overlay will not be rendered.")
        return

    try:
        root = tk.Tk()
        root.overrideredirect(True)
        try:
            root.attributes("-topmost", True)
        except tk.TclError:
            pass

        canvas = tk.Canvas(
            root,
            width=size,
            height=size,
            bg=color_hex,
            highlightthickness=0,
        )
        canvas.pack(fill="both", expand=True)

        points = [
            (0, 0),
            (0, int(size * 0.8)),
            (int(size * 0.25), int(size * 0.6)),
            (int(size * 0.5), int(size * 0.95)),
            (int(size * 0.65), int(size * 0.85)),
            (int(size * 0.4), int(size * 0.52)),
            (int(size * 0.7), int(size * 0.52)),
        ]
        flattened_points = [coord for pt in points for coord in pt]
        canvas.create_polygon(
            flattened_points,
            fill=color_hex,
            outline="#000000",
            width=2,
        )

        root.geometry(f"{size}x{size}+0+0")
        root.update()

        # Apply X11 click-through and bounding mask
        if sys.platform.startswith("linux"):
            try:
                from Xlib import display
                from Xlib.ext import shape

                d = display.Display()
                wid = root.winfo_id()
                w = d.create_resource_object("window", wid)
                rects = _build_cursor_shape_rects(size)
                w.shape_rectangles(shape.SO.Set, shape.SK.Bounding, 0, 0, 0, rects)
                w.shape_rectangles(shape.SO.Set, shape.SK.Input, 0, 0, 0, [])
                d.sync()
            except (OSError, RuntimeError) as exc:
                logger.debug(f"Could not apply X11 shape masks: {exc}")

        cur_x = 0
        cur_y = 0

        while not stop_event.is_set():
            moved = False
            try:
                while True:
                    cmd = cmd_queue.get_nowait()
                    if cmd[0] == "move":
                        cur_x, cur_y = cmd[1], cmd[2]
                        moved = True
                    elif cmd[0] == "click":
                        pressed = cmd[2]
                        fill_color = "#FFFFFF" if pressed else color_hex
                        canvas.configure(bg=fill_color)
                        moved = True
            except queue.Empty:
                pass

            if moved:
                root.geometry(f"{size}x{size}+{cur_x}+{cur_y}")

            root.update_idletasks()
            root.update()
            time.sleep(0.01)

        root.destroy()
    except (OSError, RuntimeError, tk.TclError) as exc:
        logger.debug(f"Pointer overlay thread ended with: {exc}")


class PointerOverlay:
    """Manages the host-side visual overlay for the remote user's pointer."""

    def __init__(
        self,
        color_hex: str | None = None,
        size: int | None = None,
    ):
        self._color_hex = color_hex or settings.REMOTE_POINTER_COLOR
        self._size = size or settings.REMOTE_POINTER_SIZE
        self._thread: threading.Thread | None = None
        self._queue: queue.Queue | None = None
        self._stop_event: threading.Event | None = None

    def start(self, width: int = 1920, height: int = 1080) -> None:
        """Start the pointer overlay window in a dedicated worker thread."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=_overlay_thread_entry,
            args=(self._queue, self._stop_event, self._color_hex, self._size),
            name="PointerOverlayThread",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            f"PointerOverlay started (color: {self._color_hex}, size: {self._size})."
        )

    def update_position(self, x: int, y: int) -> None:
        """Update remote pointer coordinates on the overlay."""
        if self._queue is not None:
            self._queue.put(("move", x, y))

    def show_click_feedback(self, button: str, pressed: bool) -> None:
        """Pulse pointer color to reflect click interaction."""
        if self._queue is not None:
            self._queue.put(("click", button, pressed))

    def stop(self) -> None:
        """Stop and terminate the overlay thread."""
        if self._stop_event is not None:
            self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        self._queue = None
        self._stop_event = None
        logger.info("PointerOverlay stopped.")
