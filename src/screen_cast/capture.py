import os
from dataclasses import dataclass

import mss
import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)


class ScreenCaptureError(RuntimeError):
    """Raised when the capture backend cannot produce usable frames."""


@dataclass(frozen=True, slots=True)
class ScreenInfo:
    width: int
    height: int


class ScreenCapture:
    """Captures screen frames using MSS."""

    #: Consecutive blank frames tolerated before warning the user.
    BLANK_FRAME_WARN_THRESHOLD = 30

    def __init__(self, monitor: int = 1) -> None:
        self._sct = mss.MSS()

        monitors = self._sct.monitors
        if not monitors:
            raise RuntimeError("MSS detected no monitors")

        if 1 <= monitor < len(monitors):
            selected_monitor = monitors[monitor]
        elif len(monitors) > 1:
            selected_monitor = monitors[1]
        else:
            selected_monitor = monitors[0]

        raw_width = selected_monitor["width"]
        raw_height = selected_monitor["height"]

        self._width = raw_width - (raw_width % 2)
        self._height = raw_height - (raw_height % 2)

        self._monitor = dict(selected_monitor)
        self._monitor["width"] = self._width
        self._monitor["height"] = self._height

        self._closed = False
        self._blank_frames = 0
        self._warned_blank = False

        logger.info(
            f"ScreenCapture started using MSS monitor "
            f"{selected_monitor.get('output', 'virtual')} "
            f"({self._width}x{self._height}) on a "
            f"{self._session_type()} session (DISPLAY={os.environ.get('DISPLAY')})."
        )

    @staticmethod
    def _session_type() -> str:
        return os.environ.get("XDG_SESSION_TYPE", "unknown")

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def info(self) -> ScreenInfo:
        return ScreenInfo(
            width=self._width,
            height=self._height,
        )

    def capture(self) -> np.ndarray:
        """
        Capture the current screen.
        """

        if self._closed:
            raise RuntimeError("ScreenCapture is closed")

        screenshot = self._sct.grab(self._monitor)

        frame = np.asarray(screenshot)
        self._check_usable(frame)

        return frame

    def _check_usable(self, frame: np.ndarray) -> None:
        """
        Reject frames the backend could not actually read.

        MSS grabs through X11 ``XGetImage``. On a Wayland session the X11 root
        window is only a compositor placeholder, so every grab comes back as an
        all-zero (black) buffer instead of raising. Streaming those frames
        produces a permanently blank window, so detect it up front.
        """
        if frame.size == 0:
            raise ScreenCaptureError("MSS returned an empty frame.")

        if frame.any():
            self._blank_frames = 0
            self._warned_blank = False
            return

        self._blank_frames += 1

        if self._blank_frames == 1:
            logger.error(
                f"ScreenCapture grabbed an entirely black {frame.shape} frame. "
                f"Session type is '{self._session_type()}' - MSS captures via X11, "
                "so on Wayland the compositor hides the framebuffer from X11 "
                "clients and every grab comes back blank."
            )

        if self._blank_frames >= self.BLANK_FRAME_WARN_THRESHOLD and not self._warned_blank:
            self._warned_blank = True
            raise ScreenCaptureError(
                f"ScreenCapture produced {self._blank_frames} consecutive black "
                f"frames on a '{self._session_type()}' session. MSS uses X11 "
                "XGetImage, which cannot read a Wayland compositor's output. "
                "Log in with an X11 session (e.g. 'Ubuntu on Xorg') to screen "
                "cast, or run the capture host on X11."
            )

    def close(self) -> None:
        """Release MSS resources."""

        if self._closed:
            return

        try:
            self._sct.close()
        except Exception:
            pass
        self._closed = True
