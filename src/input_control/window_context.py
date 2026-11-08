from typing import Protocol


class WindowContext(Protocol):
    """Minimal interface a renderer must expose for input capture gating and coordinate mapping."""

    @property
    def window_geometry(self) -> tuple[int, int, int, int]:
        """(screen_x, screen_y, content_w, content_h) of the CV2 window content area."""
        ...

    @property
    def is_focused(self) -> bool:
        """True when the CV2 window is the active (focused) window."""
        ...

    @property
    def source_size(self) -> tuple[int, int]:
        """(width, height) of the video frames being rendered."""
        ...
