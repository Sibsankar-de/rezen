import os
from dataclasses import dataclass
from typing import Protocol

import mss
import numpy as np

from settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class ScreenCaptureError(RuntimeError):
    """Raised when the capture backend cannot produce usable frames."""


@dataclass(frozen=True, slots=True)
class ScreenInfo:
    width: int
    height: int


class FrameSource(Protocol):
    """What the streamer needs from a capture backend."""

    @property
    def width(self) -> int: ...

    @property
    def height(self) -> int: ...

    @property
    def info(self) -> ScreenInfo: ...

    def capture(self) -> np.ndarray: ...

    def close(self) -> None: ...


def create_capture(monitor: int = 1, target_fps: int = 30) -> FrameSource:
    """Build the best available capture backend for the current session.

    MSS reads the framebuffer over X11, which returns an all-zero buffer on a
    Wayland session because the compositor keeps its output away from X11
    clients. On Wayland the portal/PipeWire backend is used instead; it needs
    the user to approve the GNOME "Share" dialog.
    """
    backend = settings.SCREEN_CAPTURE_BACKEND.lower()

    if backend != "mss":
        from screen_cast.pipewire_capture import (
            PipeWireScreenCapture,
            PipeWireUnavailable,
            portal_available,
        )

        if backend == "pipewire" or portal_available():
            try:
                return PipeWireScreenCapture(
                    max_width=settings.SCREEN_CAPTURE_MAX_WIDTH,
                    max_height=settings.SCREEN_CAPTURE_MAX_HEIGHT,
                    target_fps=target_fps,
                )
            except (PipeWireUnavailable, ScreenCaptureError) as exc:
                if backend == "pipewire":
                    raise
                logger.warning(
                    f"Portal/PipeWire capture is unavailable ({exc}); "
                    "falling back to MSS."
                )

    return ScreenCapture(monitor=monitor)


class ScreenCapture:
    """Captures screen frames using MSS."""

    #: Consecutive blank frames tolerated before warning about the backend.
    BLANK_FRAME_WARN_THRESHOLD = 30

    #: How often to repeat the warning while frames stay blank.
    BLANK_FRAME_WARN_INTERVAL = 300

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

    @property
    def blank_frames(self) -> int:
        """Consecutive all-black frames returned by the backend."""
        return self._blank_frames

    @property
    def is_producing_content(self) -> bool:
        """False when the backend only returns blank frames."""
        if self._blank_frames == 0:
            return True
        return self._blank_frames < self.BLANK_FRAME_WARN_THRESHOLD

    @property
    def warning(self) -> str | None:
        """A short hint about the backend, or None when capture looks healthy."""
        if self.is_producing_content:
            return None
        return (
            f"Capture backend returns black frames on this "
            f"'{self._session_type()}' session - MSS reads the screen via X11, "
            f"which cannot see a Wayland compositor. Remote screen will stay black "
            f"(streaming continues). Use an X11 session to capture."
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
        Warn when the backend returns frames it could not have read.

        MSS grabs through X11 ``XGetImage``. On a Wayland session the X11 root
        window is only a compositor placeholder, so every grab comes back as an
        all-zero (black) buffer instead of raising. A genuinely black screen is
        also possible, so this is reported but never fatal: the stream keeps
        running and recovers on its own as soon as real content appears.
        """
        if frame.size == 0:
            raise ScreenCaptureError("MSS returned an empty frame.")

        if frame.any():
            if self._warned_blank:
                logger.info(
                    f"ScreenCapture recovered after {self._blank_frames} blank frame(s)."
                )
            self._blank_frames = 0
            self._warned_blank = False
            return

        self._blank_frames += 1
        session = self._session_type()

        if self._blank_frames == 1:
            self._warned_blank = True
            logger.warning(
                f"ScreenCapture grabbed an entirely black {frame.shape} frame. "
                f"Session type is '{session}' - MSS captures via X11, so on Wayland "
                "the compositor hides the framebuffer from X11 clients and every "
                "grab comes back blank. Streaming continues, but the remote screen "
                "will stay black until the capture backend can read the display."
            )

        if (
            self._blank_frames >= self.BLANK_FRAME_WARN_THRESHOLD
            and self._blank_frames % self.BLANK_FRAME_WARN_INTERVAL == 0
        ):
            logger.warning(
                f"ScreenCapture is still returning black frames "
                f"({self._blank_frames} so far) on a '{session}' session. Log in "
                "with an X11 session (e.g. 'Ubuntu on Xorg') on the streaming "
                "device to get a readable framebuffer."
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
