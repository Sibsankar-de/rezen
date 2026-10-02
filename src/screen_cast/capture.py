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

        try:
            self._sct.close()
        except Exception:
            pass
        self._closed = True
