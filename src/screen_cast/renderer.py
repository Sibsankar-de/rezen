import cv2
import numpy as np

from settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class ScreenRenderer:
    """Render the frames in a window"""

    def __init__(self):
        self._closed = True
        self._window_name = settings.SCREEN_RENDER_WINDOW_NAME

    @property
    def isClosed(self) -> bool:
        return self._closed

    def start(self) -> None:
        if not self._closed:
            return

        self._closed = False
        try:
            cv2.namedWindow(self._window_name, cv2.WINDOW_NORMAL)
        except Exception as exc:
            logger.warning(f"Could not create named window immediately: {exc}")

    def display(self, frame: np.ndarray) -> bool:
        """Render the frame and display in windows"""
        if self._closed:
            return False

        try:
            cv2.imshow(winname=self._window_name, mat=frame)
            key = cv2.waitKey(1) & 0xFF

            # Close on 'q' or ESC
            if key == ord("q") or key == 27:
                self.close()
                return False

            # Detect if user closed the window by clicking the 'X' button
            prop = cv2.getWindowProperty(self._window_name, cv2.WND_PROP_VISIBLE)
            if prop < 1:
                self.close()
                return False

            return True
        except Exception as exc:
            logger.warning(f"Error displaying frame in renderer: {exc}")
            return False

    def close(self) -> None:
        """Close the window and clear"""
        if self._closed:
            return

        self._closed = True
        try:
            cv2.destroyWindow(self._window_name)
            cv2.waitKey(1)
        except Exception:
            pass
