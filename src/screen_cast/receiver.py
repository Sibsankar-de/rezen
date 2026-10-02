import asyncio
import numpy as np
from typing import Optional

from models.stream_chunk import StreamChunk, FlagType
from screen_cast.h264 import H264Decoder
from screen_cast.renderer import ScreenRenderer


class FrameBuffer:
    """Frame buffer to reassemble the bytes"""

    def __init__(self):
        self.frames: dict[str, dict[str, bytes]] = {}

    def add(self, chunk: StreamChunk) -> bytes | None:
        """Collect chunks and reconstruct the bytes"""

        frame = self.frames.setdefault(chunk.frame_id, {})
        frame[chunk.chunk_id] = chunk.data

        if chunk.flag != FlagType.END_CHUNK:
            return None

        data = b"".join(frame[chunk_id] for chunk_id in sorted(frame))

        del self.frames[chunk.frame_id]

        return data

    def clear(self):
        self.frames.clear()


class Receiver:
    """Receives streamed packets and plays"""

    def __init__(
        self,
        decoder: Optional[H264Decoder] = None,
        buffer: Optional[FrameBuffer] = None,
        renderer: Optional[ScreenRenderer] = None,
    ):
        self._running = False

        self._buffer = buffer or FrameBuffer()
        self._decoder = decoder
        self._renderer = renderer

    @property
    def decoder(self) -> H264Decoder:
        if self._decoder is None:
            self._decoder = H264Decoder()
        return self._decoder

    @property
    def renderer(self) -> ScreenRenderer:
        if self._renderer is None:
            self._renderer = ScreenRenderer()
        return self._renderer

    async def start(self) -> None:
        """Start the receiver"""
        if self._running:
            return

        self._running = True
        await asyncio.to_thread(self.renderer.start)

    async def stop(self) -> None:
        """Stops the receiver"""
        if not self._running:
            return

        self._running = False

        self._buffer.clear()
        if self._decoder is not None:
            try:
                self._decoder.close()
            except Exception:
                pass
            self._decoder = None
        if self._renderer is not None:
            try:
                self._renderer.close()
            except Exception:
                pass
            self._renderer = None

    async def handle_chunk(self, chunk: StreamChunk) -> None:
        """Handle incoming stream chunks"""

        data = self._buffer.add(chunk)

        if not data:
            return

        frames = await asyncio.to_thread(self.decoder.decode, data)

        await asyncio.to_thread(self._render_frames, frames)

        if self.renderer.isClosed:
            await self.stop()

    def _render_frames(self, frames: list[np.ndarray]):
        """Render frames using renderer"""
        for frame in frames:
            self.renderer.display(frame)

            if self.renderer.isClosed:
                break
