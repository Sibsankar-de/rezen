import multiprocessing as mp
import queue
import time
from typing import Any

import cv2
import numpy as np

from settings import settings
from utils.logger import get_logger
from utils.multiprocessing_fix import apply_multiprocessing_fix

apply_multiprocessing_fix()
logger = get_logger(__name__)


def _is_window_open(window_name: str) -> bool:
    """Check if OpenCV window is open and valid."""
    try:
        prop = cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE)
        return prop >= 0.0
    except cv2.error:
        return False
    except Exception:
        return False


def _render_process_entry(
    frame_queue: Any,
    stop_event: Any,
    window_name: str,
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

        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 960, 540)
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
    except Exception as exc:
        logger.warning(f"Error creating window in renderer process: {exc}")

    start_time = time.time()
    invisible_count = 0
    while not stop_event.is_set():
        try:
            frame = frame_queue.get(timeout=0.03)
            if frame is None:
                stop_event.set()
                break
            cv2.imshow(window_name, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                stop_event.set()
                break
        except queue.Empty:
            key = cv2.waitKey(20) & 0xFF
            if key in (ord("q"), 27):
                stop_event.set()
                break
        except Exception as exc:
            logger.warning(f"Error displaying frame in renderer process: {exc}")

        # Check if window was closed by the user (clicking 'X')
        # Only check after grace period of 3 seconds, and require consecutive failures
        if time.time() - start_time > 3.0:
            if not _is_window_open(window_name):
                invisible_count += 1
                if invisible_count >= 20:  # ~0.5s of window not existing
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

    def start(self) -> None:
        """Start the renderer process and display the window immediately."""
        if not self._closed:
            return

        self._closed = False
        apply_multiprocessing_fix()
        ctx = mp.get_context("spawn")
        self._queue = ctx.Queue(maxsize=30)
        self._stop_event = ctx.Event()

        self._process = ctx.Process(
            target=_render_process_entry,
            args=(self._queue, self._stop_event, self._window_name),
            name="ScreenRendererProcess",
            daemon=True,
        )
        self._process.start()
        logger.info(f"ScreenRenderer process started (PID: {self._process.pid}).")

    def display(self, frame: np.ndarray) -> bool:
        """Queue frame for rendering."""
        if self.isClosed or self._queue is None:
            return False

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
        logger.info("ScreenRenderer closed cleanly.")

    def _is_window_open(self) -> bool:
        """Helper to check if window is open."""
        return _is_window_open(self._window_name)
