import shutil
import subprocess
import sys
from pathlib import Path

from settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

HELPER_SCRIPT = Path(__file__).parent / "_overlay_helper.py"
SYSTEM_PYTHONS = ("/usr/bin/python3", "/usr/bin/python3.12", sys.executable)


def _find_system_python() -> str | None:
    for candidate in SYSTEM_PYTHONS:
        if Path(candidate).is_file() and shutil.which(candidate):
            return candidate
    return None


class PointerOverlay:
    """Manages the host-side visual overlay for the remote user's pointer."""

    def __init__(
        self,
        color_hex: str | None = None,
        size: int | None = None,
    ):
        self._color_hex = color_hex or settings.REMOTE_POINTER_COLOR
        self._size = size or settings.REMOTE_POINTER_SIZE
        self._proc: subprocess.Popen | None = None

    def start(self, width: int = 1920, height: int = 1080) -> None:
        """Start the GTK3 RGBA pointer overlay helper process."""
        if self._proc is not None and self._proc.poll() is None:
            return

        python_bin = _find_system_python()
        if not python_bin:
            logger.debug("No Python interpreter found for overlay helper.")
            return

        try:
            self._proc = subprocess.Popen(
                [python_bin, str(HELPER_SCRIPT), self._color_hex, str(self._size)],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
            logger.info(
                f"PointerOverlay started (color: {self._color_hex}, size: {self._size})."
            )
        except (OSError, RuntimeError) as exc:
            logger.debug(f"Could not start overlay helper process: {exc}")
            self._proc = None

    def update_position(self, x: int, y: int) -> None:
        """Update remote pointer coordinates on the overlay."""
        if self._proc is not None and self._proc.stdin and self._proc.poll() is None:
            try:
                self._proc.stdin.write(f"move {x} {y}\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError):
                self._proc = None

    def show_click_feedback(self, button: str, pressed: bool) -> None:
        """Pulse pointer color to reflect click interaction."""
        if self._proc is not None and self._proc.stdin and self._proc.poll() is None:
            try:
                val = "1" if pressed else "0"
                self._proc.stdin.write(f"click {button} {val}\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError):
                self._proc = None

    def stop(self) -> None:
        """Stop and terminate the overlay helper process."""
        if self._proc is not None:
            try:
                if self._proc.stdin and self._proc.poll() is None:
                    self._proc.stdin.write("quit\n")
                    self._proc.stdin.flush()
                self._proc.wait(timeout=0.5)
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                if self._proc.poll() is None:
                    self._proc.terminate()
            self._proc = None
        logger.info("PointerOverlay stopped.")
