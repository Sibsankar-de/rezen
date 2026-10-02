import queue
import threading
import time

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

    @property
    def isClosed(self) -> bool:
        return self._closed

    def start(self) -> None:
        """Start the renderer thread and open the render window."""
        if not self._closed:
            return

        self._closed = False
        self._thread = threading.Thread(
            target=self._render_loop, name="ScreenRendererThread", daemon=True
        )
        self._thread.start()

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
        """Check if OpenCV window is open and valid."""
        try:
            prop = cv2.getWindowProperty(self._window_name, cv2.WND_PROP_VISIBLE)
            return prop >= 0.0
        except cv2.error:
            return False
        except Exception:
            return False

    def _render_loop(self) -> None:
        """Dedicated render thread body handling all OpenCV GUI operations."""
        window_created = False
        try:
            try:
                cv2.startWindowThread()
            except Exception:
                pass

            cv2.namedWindow(self._window_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self._window_name, 960, 540)
            window_created = True

            # Initial placeholder frame (open immediately even when no frames yet)
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
            cv2.imshow(self._window_name, placeholder)
            for _ in range(4):
                cv2.waitKey(15)
            logger.info("ScreenRenderer window opened successfully.")
        except Exception as exc:
            logger.warning(f"Could not create named window in ScreenRenderer: {exc}")

        start_time = time.time()
        invisible_count = 0
        try:
            while not self._closed:
                try:
                    frame = self._queue.get(timeout=0.03)
                except queue.Empty:
                    # Pump events periodically even when idle/waiting for frames to prevent OS "Not Responding"
                    if window_created and not self._closed:
                        try:
                            key = cv2.waitKey(20) & 0xFF
                            if key in (ord("q"), 27):
                                logger.info("User requested exit from renderer window.")
                                self._closed = True
                                break
                            # Only check for window close after initial grace period
                            if time.time() - start_time > 3.0:
                                if not self._is_window_open():
                                    invisible_count += 1
                                    if invisible_count >= 50:
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

                    if time.time() - start_time > 3.0:
                        if not self._is_window_open():
                            invisible_count += 1
                            if invisible_count >= 50:
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
