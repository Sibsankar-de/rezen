import queue
import threading

import cv2
import numpy as np

from settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class ScreenRenderer:
    """Render the frames in a dedicated window thread."""

    def __init__(self):
        self._closed = True
        self._window_name = settings.SCREEN_RENDER_WINDOW_NAME
        self._queue: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=30)
        self._thread: threading.Thread | None = None
        self._ready_event = threading.Event()

    @property
    def isClosed(self) -> bool:
        return self._closed

    def start(self) -> None:
        """Start the renderer thread and open the render window."""
        if not self._closed:
            return

        self._closed = False
        self._ready_event.clear()
        self._thread = threading.Thread(
            target=self._render_loop, name="ScreenRendererThread", daemon=True
        )
        self._thread.start()
        # Wait up to 2 seconds for window to be created
        if not self._ready_event.wait(timeout=2.0):
            logger.warning("ScreenRenderer window initialization timed out")

    def display(self, frame: np.ndarray) -> bool:
        """Queue frame for rendering."""
        if self._closed:
            return False

        # Drop oldest frame if queue is full to avoid latency build-up
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass

        try:
            self._queue.put_nowait(frame)
            return True
        except queue.Full:
            return False

    def close(self) -> None:
        """Signal the render thread to stop and clean up."""
        if self._closed:
            return

        self._closed = True
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def _is_window_open(self) -> bool:
        """Check if OpenCV window is open and visible."""
        try:
            prop = cv2.getWindowProperty(self._window_name, cv2.WND_PROP_VISIBLE)
            return prop >= 1.0
        except Exception:
            return False

    def _render_loop(self) -> None:
        """Dedicated render thread body handling all OpenCV GUI operations."""
        window_created = False
        try:
            cv2.namedWindow(self._window_name, cv2.WINDOW_NORMAL)
            window_created = True

            # Initial placeholder frame
            placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(
                placeholder,
                "Screen Cast Connected",
                (140, 220),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                placeholder,
                "Waiting for video frames...",
                (160, 270),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (180, 180, 180),
                1,
                cv2.LINE_AA,
            )
            cv2.imshow(self._window_name, placeholder)
            cv2.waitKey(1)
        except Exception as exc:
            logger.warning(f"Could not create named window in ScreenRenderer: {exc}")
        finally:
            self._ready_event.set()

        invisible_count = 0
        try:
            while not self._closed:
                try:
                    frame = self._queue.get(timeout=0.03)
                except queue.Empty:
                    # Pump events periodically even when idle to prevent OS "Not Responding"
                    if window_created and not self._closed:
                        try:
                            key = cv2.waitKey(20) & 0xFF
                            if key in (ord("q"), 27):
                                logger.info("User requested exit from renderer window.")
                                self._closed = True
                                break
                            if not self._is_window_open():
                                invisible_count += 1
                                if invisible_count >= 10:
                                    logger.info("Renderer window closed by user.")
                                    self._closed = True
                                    break
                            else:
                                invisible_count = 0
                        except Exception:
                            pass
                    continue

                if frame is None or self._closed:
                    break

                try:
                    cv2.imshow(winname=self._window_name, mat=frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord("q"), 27):
                        logger.info("User pressed exit key in renderer window.")
                        self._closed = True
                        break

                    if not self._is_window_open():
                        invisible_count += 1
                        if invisible_count >= 10:
                            logger.info("Renderer window closed by user.")
                            self._closed = True
                            break
                    else:
                        invisible_count = 0
                except Exception as exc:
                    logger.warning(f"Error displaying frame in renderer: {exc}")
        except Exception as exc:
            logger.error(f"Unexpected error in ScreenRenderer loop: {exc}", exc_info=True)
        finally:
            if window_created:
                try:
                    cv2.destroyWindow(self._window_name)
                    for _ in range(4):
                        cv2.waitKey(1)
                except Exception:
                    pass
            self._closed = True
