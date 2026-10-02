import asyncio

from models.stream_chunk import FlagType, StreamChunk
from screen_cast.h264 import H264Decoder
from screen_cast.renderer import ScreenRenderer
from utils.logger import get_logger

logger = get_logger(__name__)


def _chunk_sort_key(chunk_id: str) -> int:
    try:
        return int(chunk_id.split("_")[-1])
    except (ValueError, IndexError):
        return 0


class FrameBuffer:
    """Frame buffer to reassemble the bytes"""

    def __init__(self):
        self.frames: dict[str, dict[str, bytes]] = {}

    def add(self, chunk: StreamChunk) -> bytes | None:
        """Collect chunks and reconstruct the bytes"""
        frame = self.frames.setdefault(chunk.frame_id, {})
        frame[chunk.chunk_id] = chunk.data

        # If not marked as end chunk and we don't yet have all chunks, wait for more
        if chunk.flag != FlagType.END_CHUNK and len(frame) < chunk.total_chunks:
            return None

        # Clean up stale uncompleted frames if buffer grows too large
        if len(self.frames) > 50:
            oldest_keys = list(self.frames.keys())[:-30]
            for old_key in oldest_keys:
                del self.frames[old_key]

        # Incomplete frame due to dropped chunks
        if len(frame) < chunk.total_chunks:
            del self.frames[chunk.frame_id]
            return None

        # Sort chunks numerically by chunk index
        sorted_keys = sorted(frame.keys(), key=_chunk_sort_key)
        data = b"".join(frame[cid] for cid in sorted_keys)

        del self.frames[chunk.frame_id]

        return data

    def clear(self):
        self.frames.clear()


class Receiver:
    """Receives streamed packets and plays"""

    def __init__(
        self,
        decoder: H264Decoder | None = None,
        buffer: FrameBuffer | None = None,
        renderer: ScreenRenderer | None = None,
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
        self.renderer.start()

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
        if not self._running:
            return

        data = self._buffer.add(chunk)

        if not data:
            return

        try:
            frames = await asyncio.to_thread(self.decoder.decode, data)
            if frames:
                for frame in frames:
                    if not self.renderer.display(frame):
                        break
        except Exception as exc:
            logger.error(f"Error decoding or rendering chunk: {exc}", exc_info=True)

        if self.renderer.isClosed:
            await self.stop()
