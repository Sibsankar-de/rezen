import collections
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import numpy as np

from screen_cast.capture import ScreenCaptureError, ScreenInfo
from utils.logger import get_logger

logger = get_logger(__name__)

HELPER_SCRIPT = Path(__file__).parent / "_portal_grab.py"

#: Candidates for the interpreter that owns the D-Bus/GLib bindings.
SYSTEM_PYTHONS = ("/usr/bin/python3", "/usr/bin/python3.12", "/usr/bin/python")

#: How long to wait for the user to approve the GNOME "Share" dialog.
CONSENT_TIMEOUT_SECONDS = 120.0

#: How long to wait for the first frame to arrive from GStreamer.
FIRST_FRAME_TIMEOUT_SECONDS = 15.0

#: How long a single capture call waits for a fresh frame before repeating the
#: previous one. Keeps the pipeline paced without building latency.
FRAME_WAIT_SECONDS = 0.05

#: Frame rate requested from the compositor before scaling.
TARGET_FPS = 30

#: Media classes that identify a screen/compositor video output.
SCREEN_MEDIA_CLASSES = ("Stream/Output/Video", "Video/Screen")

#: Node names used by common Wayland compositors, preferred when several
#: applications expose a screen-class video node.
COMPOSITOR_NAME_HINTS = (
    "gnome-shell",
    "kwin_wayland",
    "mutter",
    "wlroots",
    "sway",
    "weston",
    "wayfire",
    "hyprland",
    "niri",
    "cage",
    "labwc",
    "swaylock",
)


def discover_screen_node() -> str | None:
    """Return the name of the compositor's screen video node.

    Binding the pipeline to this node rather than letting PipeWire autoconnect
    keeps the capture pinned to the screen.
    """
    try:
        dumped = subprocess.run(
            ["pw-dump"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning(f"Could not inspect PipeWire for the screen node: {exc}")
        return None

    if dumped.returncode != 0:
        logger.warning("pw-dump failed; falling back to automatic PipeWire binding.")
        return None

    try:
        objects = json.loads(dumped.stdout)
    except ValueError as exc:
        logger.warning(f"Could not parse pw-dump output: {exc}")
        return None

    candidates: list[str] = []
    for obj in objects:
        if obj.get("type") != "PipeWire:Interface:Node":
            continue
        props = obj.get("info", {}).get("props", {})
        if props.get("media.class") not in SCREEN_MEDIA_CLASSES:
            continue
        name = props.get("node.name")
        if not name:
            continue
        if any(hint in str(name).lower() for hint in COMPOSITOR_NAME_HINTS):
            return str(name)
        candidates.append(str(name))

    if len(candidates) == 1:
        return candidates[0]

    if candidates:
        logger.warning(
            f"Multiple screen-class video nodes found ({candidates}); using "
            "automatic PipeWire binding."
        )
    return None


class PipeWireUnavailable(RuntimeError):
    """The Wayland portal/PipeWire capture path cannot be used here."""


def find_system_python() -> str | None:
    """Locate a Python interpreter that can import ``dbus`` and ``gi``."""
    for candidate in SYSTEM_PYTHONS:
        if not os.path.exists(candidate):
            continue
        try:
            probe = subprocess.run(
                [candidate, "-c", "import dbus, gi"],
                capture_output=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if probe.returncode == 0:
            return candidate
    return None


def portal_available() -> bool:
    """True when this looks like a Wayland session with the ScreenCast portal."""
    if os.environ.get("XDG_SESSION_TYPE", "").lower() != "wayland":
        return False
    if not os.environ.get("XDG_RUNTIME_DIR"):
        return False
    if find_system_python() is None:
        logger.warning(
            "Wayland session detected but no system Python with the D-Bus/GLib "
            "bindings was found (needed for the screen-share portal)."
        )
        return False
    return True


class PipeWireScreenCapture:
    """Captures the screen on Wayland via the portal and a PipeWire stream.

    Two helpers are used:

    * ``_portal_grab.py`` runs under the system Python and holds the D-Bus
      screen-share request open, which is what keeps the PipeWire stream alive.
    * ``gst-launch-1.0`` runs a ``pipewiresrc`` pipeline that emits raw BGRA
      frames on stdout, which are read here and exposed as numpy arrays.

    The GStreamer pipeline is the only supported way to read a portal stream
    with the packages available on this platform: ``pw-cat`` is audio only and
    the GStreamer PipeWire plugin exposes no node selection, but it does bind
    to the portal stream automatically while it exists.
    """

    def __init__(
        self,
        max_width: int = 1920,
        max_height: int = 1080,
        target_fps: int = TARGET_FPS,
    ) -> None:
        gst_launch = shutil.which("gst-launch-1.0")
        if gst_launch is None:
            raise PipeWireUnavailable("gst-launch-1.0 is not installed")

        python = find_system_python()
        if python is None:
            raise PipeWireUnavailable(
                "no system Python with D-Bus/GLib bindings is available"
            )

        self._target_fps = max(1, target_fps)
        self._gst_launch = gst_launch
        self._python = python
        self._helper: subprocess.Popen | None = None
        self._gst: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()
        self._latest: collections.deque[np.ndarray] = collections.deque(maxlen=1)
        self._last_frame: np.ndarray | None = None
        self._reader_error: str | None = None
        self._closed = False

        self._node_id, self._source_width, self._source_height = self._request_stream()

        # Pin the capture to the compositor's screen node. Falls back to
        # PipeWire autoconnect if it cannot be identified.
        self._screen_node = discover_screen_node()
        if self._screen_node:
            logger.info(
                f"Screen capture will bind to PipeWire node '{self._screen_node}'."
            )
        else:
            logger.warning(
                "Could not identify the compositor's screen node; letting "
                "PipeWire bind automatically."
            )
        self._width, self._height = self._scaled_size(
            self._source_width, self._source_height, max_width, max_height
        )
        self._frame_size = self._width * self._height * 4

        logger.info(
            f"PipeWire capture negotiated {self._width}x{self._height} from a "
            f"{self._source_width}x{self._source_height} portal screen stream "
            f"(portal node {self._node_id})."
        )

        self._start_pipeline()

    @staticmethod
    def _scaled_size(src_w: int, src_h: int, max_w: int, max_h: int) -> tuple[int, int]:
        """Fit the source inside the cap, keeping aspect ratio and even edges."""
        scale = min(max_w / src_w, max_h / src_h, 1.0)
        width = max(2, int(src_w * scale) // 2 * 2)
        height = max(2, int(src_h * scale) // 2 * 2)
        return width, height

    def _request_stream(self) -> tuple[int, int, int]:
        """Ask the portal for a monitor stream, waiting for user consent."""
        logger.info(
            "Requesting a screen-share stream from the XDG Desktop Portal. "
            "Approve the GNOME 'Share' dialog to continue."
        )

        try:
            self._helper = subprocess.Popen(
                [self._python, str(HELPER_SCRIPT)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=1,
                text=True,
            )
        except OSError as exc:
            raise PipeWireUnavailable(f"could not start the portal helper: {exc}")

        assert self._helper.stdin is not None
        assert self._helper.stdout is not None

        self._helper.stdin.write(json.dumps({"cmd": "grab"}) + "\n")
        self._helper.stdin.flush()

        deadline = time.monotonic() + CONSENT_TIMEOUT_SECONDS
        while True:
            if time.monotonic() > deadline:
                self.close()
                raise ScreenCaptureError(
                    "Timed out waiting for screen-share consent. Approve the "
                    "'Share' dialog, or log in with an X11 session."
                )

            line = self._helper.stdout.readline()
            if not line:
                self.close()
                raise ScreenCaptureError(
                    "The screen-share portal helper exited unexpectedly."
                )

            try:
                message = json.loads(line)
            except ValueError:
                continue

            if message.get("ready"):
                logger.info(
                    f"Screen-share consent granted; PipeWire node "
                    f"{message.get('node_id')} is streaming."
                )
                return (
                    int(message["node_id"]),
                    int(message["width"]),
                    int(message["height"]),
                )

            if message.get("error"):
                self.close()
                raise ScreenCaptureError(
                    f"Screen-share request failed: {message['error']}"
                )

    def _start_pipeline(self) -> None:
        """Run the GStreamer pipeline that turns the PipeWire stream into frames."""
        command = [
            self._gst_launch,
            "-q",
            "pipewiresrc",
            # Pin the capture to the compositor's screen node.
            *([f"target-object={self._screen_node}"] if self._screen_node else []),
            "!",
            "videoconvert",
            "!",
            "videoscale",
            # Nearest-neighbour downscaling drops pixels instead of averaging
            # them, which shimmers badly on text. Bilinear is far cleaner and
            # costs little next to the conversion.
            "method=bilinear",
            "!",
            f"video/x-raw,format=BGRA,width={self._width},height={self._height}",
            "!",
            "fdsink",
        ]
        try:
            self._gst = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                # Surface pipeline failures when GST_DEBUG is set.
                stderr=None if os.environ.get("GST_DEBUG") else subprocess.DEVNULL,
                # Buffered so read1() can hand back partial frames without
                # blocking for a whole one.
                bufsize=-1,
            )
        except OSError as exc:
            self.close()
            raise PipeWireUnavailable(f"could not start gstreamer: {exc}")

        self._reader = threading.Thread(
            target=self._read_frames, name="PipeWireFrameReader", daemon=True
        )
        self._reader.start()

    def _read_frames(self) -> None:
        """Continuously drain the pipeline, keeping only the newest frame."""
        assert self._gst is not None and self._gst.stdout is not None
        stdout = self._gst.stdout
        frame_size = self._frame_size
        buffer = bytearray()
        offset = 0

        while not self._stop.is_set():
            try:
                chunk = stdout.read1(frame_size)
            except (OSError, ValueError) as exc:
                if not self._stop.is_set():
                    self._reader_error = f"read failed: {exc}"
                return

            if not chunk:
                if not self._stop.is_set():
                    self._reader_error = "the screen-share stream ended"
                return

            buffer.extend(chunk)

            while len(buffer) - offset >= frame_size:
                frame = np.frombuffer(
                    bytes(buffer[offset : offset + frame_size]), dtype=np.uint8
                ).reshape(self._height, self._width, 4)
                offset += frame_size
                # Keep only the newest frame so latency stays bounded.
                self._latest.clear()
                self._latest.append(frame)

            if offset:
                # Drop consumed bytes without repeatedly shifting the whole
                # buffer, which would make large frames cost O(n^2).
                del buffer[:offset]
                offset = 0

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def info(self) -> ScreenInfo:
        return ScreenInfo(width=self._width, height=self._height)

    def capture(self) -> np.ndarray:
        """Return the newest frame.

        Waits briefly for a fresh frame so the stream stays paced at the
        capture rate. If the screen-share stream has not produced anything new
        in that window the previous frame is returned again: repeating a frame
        costs almost nothing to encode, and it keeps the pipeline alive if the
        compositor stops producing (idle screen, static desktop).
        """
        if self._closed:
            raise RuntimeError("PipeWireScreenCapture is closed")

        frame = self._take_new_frame(FRAME_WAIT_SECONDS)
        if frame is not None:
            self._last_frame = frame
            return frame

        if self._last_frame is not None:
            return self._last_frame

        # Nothing seen yet: block until the stream produces its first frame.
        first_deadline = time.monotonic() + FIRST_FRAME_TIMEOUT_SECONDS
        while self._last_frame is None:
            frame = self._take_new_frame(max(0.0, first_deadline - time.monotonic()))
            if frame is not None:
                self._last_frame = frame
                return frame
            if self._last_frame is not None:
                return self._last_frame
            if time.monotonic() >= first_deadline:
                break

        raise ScreenCaptureError("No frames received from the screen-share stream.")

    def _take_new_frame(self, timeout: float) -> np.ndarray | None:
        """Pop the newest frame if one arrives within ``timeout`` seconds."""
        deadline = time.monotonic() + timeout

        while True:
            if self._latest:
                return self._latest.popleft()

            self._raise_if_broken()

            if time.monotonic() >= deadline:
                return None
            time.sleep(0.003)

    def _raise_if_broken(self) -> None:
        """Surface a dead reader or pipeline as an error."""
        if self._reader_error:
            error, self._reader_error = self._reader_error, None
            self.close()
            raise ScreenCaptureError(
                f"Screen-share stream is not delivering frames: {error}"
            )
        if self._gst is not None and self._gst.poll() is not None:
            self.close()
            raise ScreenCaptureError(
                "The GStreamer screen-share pipeline exited unexpectedly."
            )

    def close(self) -> None:
        """Tear down the GStreamer pipeline and the portal session."""
        if self._closed and self._helper is None and self._gst is None:
            return

        self._closed = True
        self._stop.set()

        for proc in (self._gst, self._helper):
            if proc is None or proc.poll() is not None:
                continue
            try:
                if proc.stdin is not None:
                    proc.stdin.close()
            except OSError:
                pass
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except (OSError, subprocess.SubprocessError):
                try:
                    proc.kill()
                except OSError:
                    pass

        self._gst = None
        self._helper = None
        logger.info("PipeWire screen capture stopped.")
