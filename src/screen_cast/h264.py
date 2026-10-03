from dataclasses import dataclass
from fractions import Fraction
from typing import Any

import numpy as np

from settings import settings

av: Any = None


def _av() -> Any:
    """Import PyAV lazily and cache the module.

    PyAV bundles its own FFmpeg shared libraries. When they are loaded into the
    same process as OpenCV's HighGUI, ``cv2.namedWindow`` spins forever at 100%
    CPU and never creates a window. The ScreenRenderer runs in a spawned child
    process that re-imports the application modules, so PyAV must stay out of
    that process until a codec is actually needed.
    """
    global av
    if av is None:
        import av as av_module

        av = av_module
    return av


@dataclass(slots=True)
class EncodedPacket:
    data: bytes
    pts: int | None
    dts: int | None
    is_keyframe: bool


class H264Encoder:
    """Synchronous H.264 encoder for screen frames."""

    def __init__(
        self,
        width: int,
        height: int,
        fps: int = 30,
        bitrate: int | None = None,
        preset: str | None = None,
        tune: str = "zerolatency",
    ) -> None:
        self.width = width - (width % 2)
        self.height = height - (height % 2)
        self.fps = fps
        self.bitrate = bitrate or settings.SCREEN_STREAM_BITRATE
        self.preset = preset or settings.SCREEN_STREAM_PRESET

        self._closed = False
        self._pts = 0

        self._codec = _av().CodecContext.create("libx264", "w")

        self._codec.width = self.width
        self._codec.height = self.height
        self._codec.pix_fmt = "yuv420p"

        self._codec.time_base = Fraction(1, fps)
        self._codec.framerate = Fraction(fps, 1)
        self._codec.gop_size = fps

        self._codec.bit_rate = self.bitrate

        # Keep deblocking and CABAC on: the ultrafast preset turns both off and
        # produces visible blocking artefacts on text. Lookahead stays off via
        # the zerolatency tune because this is a live stream.
        self._codec.options = {
            "preset": self.preset,
            "tune": tune,
            "profile": "high",
        }

        self._codec.open()

    def encode(self, frame: np.ndarray) -> list[EncodedPacket]:
        """Encode one MSS BGRA frame."""

        if self._closed:
            raise RuntimeError("Encoder is closed")

        if frame.shape[0] != self.height or frame.shape[1] != self.width:
            if frame.shape[0] >= self.height and frame.shape[1] >= self.width:
                frame = frame[:self.height, :self.width]
            else:
                expected_shape = (self.height, self.width, 4)
                raise ValueError(f"Expected {expected_shape}, got {frame.shape}")

        if not frame.flags["C_CONTIGUOUS"]:
            frame = np.ascontiguousarray(frame)

        video_frame = _av().VideoFrame.from_ndarray(
            frame,
            format="bgra",
        )

        video_frame.pts = self._pts
        self._pts += 1

        return [
            EncodedPacket(
                data=bytes(packet),
                pts=packet.pts,
                dts=packet.dts,
                is_keyframe=packet.is_keyframe,
            )
            for packet in self._codec.encode(video_frame)
        ]

    def flush(self) -> list[EncodedPacket]:
        """Return any packets buffered by the encoder."""

        if self._closed:
            return []

        try:
            return [
                EncodedPacket(
                    data=bytes(packet),
                    pts=packet.pts,
                    dts=packet.dts,
                    is_keyframe=packet.is_keyframe,
                )
                for packet in self._codec.encode(None)
            ]
        except Exception:
            return []

    def close(self) -> None:
        """Flush and release encoder resources."""

        if self._closed:
            return

        try:
            self.flush()
        except Exception:
            pass

        try:
            self._codec.close()
        except Exception:
            pass

        self._closed = True


class H264Decoder:
    """Synchronous H.264 decoder using PyAV."""

    def __init__(self) -> None:
        self._closed = False

        self._codec = _av().CodecContext.create(
            "h264",
            "r",
        )

    def decode(self, data: bytes) -> list[np.ndarray]:
        """
        Decode a complete H.264 encoded data unit.
        """

        if self._closed:
            raise RuntimeError("Decoder is closed")

        if not data:
            return []

        try:
            packet = _av().Packet(data)
            frames = self._codec.decode(packet)
            return [frame.to_ndarray(format="bgr24") for frame in frames]
        except Exception:
            return []

    def flush(self) -> list[np.ndarray]:
        """
        Flush any frames buffered by the decoder.
        """

        if self._closed:
            return []

        try:
            frames = self._codec.decode(None)
            return [frame.to_ndarray(format="bgr24") for frame in frames]
        except Exception:
            return []

    def close(self) -> None:
        """Release decoder resources."""

        if self._closed:
            return

        try:
            self.flush()
        except Exception:
            pass

        try:
            self._codec.close()
        except Exception:
            pass

        self._closed = True
