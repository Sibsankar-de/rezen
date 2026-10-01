from dataclasses import dataclass

import av
import numpy as np


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
        bitrate: int = 4_000_000,
        preset: str = "ultrafast",
        tune: str = "zerolatency",
    ) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.bitrate = bitrate

        self._closed = False
        self._pts = 0

        self._codec = av.CodecContext.create("libx264", "w")

        self._codec.width = width
        self._codec.height = height
        self._codec.pix_fmt = "yuv420p"

        self._codec.time_base = av.Rational(1, fps)
        self._codec.framerate = av.Rational(fps, 1)

        self._codec.bit_rate = bitrate

        self._codec.options = {
            "preset": preset,
            "tune": tune,
        }

        self._codec.open()

    def encode(self, frame: np.ndarray) -> list[EncodedPacket]:
        """Encode one MSS BGRA frame."""

        if self._closed:
            raise RuntimeError("Encoder is closed")

        expected_shape = (self.height, self.width, 4)

        if frame.shape != expected_shape:
            raise ValueError(f"Expected {expected_shape}, got {frame.shape}")

        video_frame = av.VideoFrame.from_ndarray(
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

        return [
            EncodedPacket(
                data=bytes(packet),
                pts=packet.pts,
                dts=packet.dts,
                is_keyframe=packet.is_keyframe,
            )
            for packet in self._codec.encode(None)
        ]

    def close(self) -> None:
        """Flush and release encoder resources."""

        if self._closed:
            return

        self.flush()
        self._codec.close()
        self._closed = True


class H264Decoder:
    """Synchronous H.264 decoder using PyAV."""

    def __init__(self) -> None:
        self._closed = False

        self._codec = av.CodecContext.create(
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

        packet = av.Packet(data)

        frames = self._codec.decode(packet)

        return [frame.to_ndarray(format="bgr24") for frame in frames]

    def flush(self) -> list[np.ndarray]:
        """
        Flush any frames buffered by the decoder.
        """

        if self._closed:
            return []

        frames = self._codec.decode(None)

        return [frame.to_ndarray(format="bgr24") for frame in frames]

    def close(self) -> None:
        """Release decoder resources."""

        if self._closed:
            return

        self.flush()
        self._codec.close()

        self._closed = True
