import cv2
import numpy as np

from settings import settings


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

        cv2.namedWindow(self._window_name, cv2.WINDOW_NORMAL)
        self._closed = False

    def display(self, frame: np.ndarray) -> bool:
        """Render the frame and display in windows"""

        if self._closed:
            return False

        cv2.imshow(winname=self._window_name, mat=frame)

        key = cv2.waitKey(1) & 0xFF

        return True

    def close(self) -> None:
        """Close the window and clear"""
        if self._closed:
            return

        cv2.destroyWindow(self._window_name)
        self._closed = True
