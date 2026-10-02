import asyncio
import numpy as np
from typing import Optional, Callable, Awaitable, Any

from screen_cast.capture import ScreenCapture
from screen_cast.h264 import H264Encoder
from models.stream_chunk import StreamChunk, ChunkType, FlagType

from settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class Streamer:
    """Handle streaming of screen"""

    def __init__(
        self,
        capture: Optional[ScreenCapture] = None,
        encoder: Optional[H264Encoder] = None,
        queue_size: int = settings.STREAM_QUEUE_MAX_SIZE,
    ):
        self._capture = capture
        self._encoder = encoder
        self._queue_size = queue_size

        self._frame_queue: asyncio.Queue[np.ndarray] = asyncio.Queue(maxsize=queue_size)

        self._running = False

        self._capture_task: asyncio.Task | None = None
        self._encode_task: asyncio.Task | None = None

        self._frame_index = 0

    @property
    def capture(self) -> ScreenCapture:
        if self._capture is None:
            self._capture = ScreenCapture()
        return self._capture

    @property
    def encoder(self) -> H264Encoder:
        if self._encoder is None:
            self._encoder = H264Encoder(self.capture.width, self.capture.height)
        return self._encoder

    async def start(self, send: Callable[[StreamChunk], Awaitable[None]]) -> None:
        """Starts the streamer and start producer consumer"""

        if self._running:
            return

        self._running = True
        self._send = send

        self._capture_task = asyncio.create_task(self._capture_loop())
        self._encode_task = asyncio.create_task(self._encode_loop())

    async def stop(self) -> None:
        """Stop the streamer and cancel tasks"""

        if not self._running:
            return

        self._running = False

        if self._capture_task is not None:
            self._capture_task.cancel()
        if self._encode_task is not None:
            self._encode_task.cancel()

        await self._clear_queue()

        tasks = [t for t in (self._capture_task, self._encode_task) if t is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        if self._capture is not None:
            try:
                self._capture.close()
            except Exception:
                pass
            self._capture = None

        if self._encoder is not None:
            try:
                self._encoder.close()
            except Exception:
                pass
            self._encoder = None

    async def _capture_loop(self) -> None:
        """Captures the frames and push into queue"""

        while self._running:
            try:
                frame = await asyncio.to_thread(self.capture.capture)
                await self._frame_queue.put(frame)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.error("Error in screen capture loop", exc_info=True)
                break

    async def _encode_loop(self) -> None:
        """Consume queue and encode and send frames"""

        while self._running:
            try:
                frame = await self._frame_queue.get()
            except asyncio.CancelledError:
                break

            try:
                await self._encode_and_send_chunk(frame)
            except asyncio.CancelledError:
                self._frame_queue.task_done()
                break
            except Exception:
                logger.error("Error in screen encode loop", exc_info=True)
            finally:
                self._frame_queue.task_done()

    async def _encode_and_send_chunk(self, frame: np.ndarray):
        """Encode frame, create chunks and send chunks"""
        packets = await asyncio.to_thread(self.encoder.encode, frame)

        for packet in packets:
            chunks = self._create_chunks(packet.data, settings.STREAM_CHUNK_SIZE)

            for chunk_index, data in enumerate(chunks):
                chunk_falg = FlagType.MEDIATE_CHUNK

                if chunk_index == 0:
                    chunk_falg = FlagType.START_CHUNK
                elif chunk_index == len(chunks) - 1:
                    chunk_falg = FlagType.END_CHUNK

                stream_chunk = StreamChunk(
                    frame_id=f"frame_{self._frame_index}",
                    chunk_id=f"chunk_{chunk_index}",
                    data=data,
                    size=len(data),
                    total_chunks=len(chunks),
                    type=ChunkType.VIDEO,
                    flag=chunk_falg,
                )

                # send the chunk
                await self._send(stream_chunk)

            self._frame_index += 1

    def _create_chunks(self, data: bytes, chunk_size: int) -> list[bytes]:
        """Split frame bytes and create chunks"""
        return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]

    async def _clear_queue(self) -> None:
        """Removes all elements from the queue"""
        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
                self._frame_queue.task_done()
            except (asyncio.QueueEmpty, ValueError):
                break
