from dataclasses import dataclass

import mss
import numpy as np


@dataclass(frozen=True, slots=True)
class ScreenInfo:
    width: int
    height: int


class ScreenCapture:
    """Captures screen frames using MSS."""

    def __init__(self, monitor: int = 1) -> None:
        self._sct = mss.mss()

        monitors = self._sct.monitors

        if monitor < 1 or monitor >= len(monitors):
            raise ValueError(
                f"Invalid monitor {monitor}. "
                f"Available monitors: 1-{len(monitors) - 1}"
            )

        self._monitor = monitors[monitor]

        self._width = self._monitor["width"]
        self._height = self._monitor["height"]

        self._closed = False

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

        return np.asarray(screenshot)

    def close(self) -> None:
        """Release MSS resources."""

        if self._closed:
            return

        self._sct.close()
        self._closed = True
