import asyncio
import numpy as np
from typing import Optional, Callable, Awaitable, Any

from screen_cast.capture import ScreenCapture
from screen_cast.encoder import H264Encoder
from models.stream_chunk import StreamChunk, ChunkType, FlagType

from settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class Streamer:
    """Handle streaming of screen"""

    def __init__(
        self,
        send: Callable[[Any], Awaitable[Any]],
        capture: Optional[ScreenCapture],
        encoder: Optional[H264Encoder],
        queue_size: int = settings.STREAM_QUEUE_MAX_SIZE,
    ):
        self._send = send
        self._capture = capture
        self._encoder = encoder

        self._frame_queue: asyncio.Queue[np.ndarray] = asyncio.Queue(maxsize=queue_size)

        self._running = False

        if self._capture is None:
            self._capture = ScreenCapture()

        if self._encoder is None:
            self._encoder = H264Encoder(self._capture.width, self._capture.height)

        self._capture_task: asyncio.Task
        self._encode_task: asyncio.Task

        self._frame_index = 0

    async def start(self) -> None:
        """Starts the streamer and start producer consumer"""

        if self._running:
            return

        self._running = True

        self._capture_task = asyncio.create_task(self._capture_loop)
        self._encode_task = asyncio.create_task(self._encode_loop)

        await asyncio.gather(self._capture_task, self._encode_task)

    async def stop(self) -> None:
        """Stop the streamer and cancel tasks"""

        if not self._running:
            return

        self._running = False

        self._capture_task.cancel()
        self._encode_task.cancel()

        await asyncio.gather(
            self._capture_task, self._encode_task, return_exceptions=True
        )

    async def _capture_loop(self) -> None:
        """Captures the frames and push into queue"""

        while self._running and not self._frame_queue.full():
            frame = await asyncio.to_thread(self._capture.capture)

            await self._frame_queue.put(frame)

    async def _encode_loop(self) -> None:
        """Consume queue and encode and send frames"""

        while self._running and not self._frame_queue.empty():
            frame = await self._frame_queue.get()

            await self._encode_and_send_chunk(frame)

    async def _encode_and_send_chunk(self, frame: np.ndarray):
        """Encode frame, create chunks and send chunks"""
        try:
            packets = await asyncio.to_thread(self._encoder.encode, frame)

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
        finally:
            self._frame_queue.task_done()

    def _create_chunks(self, data: bytes, chunk_size: int) -> list[bytes]:
        """Split frame bytes and create chunks"""
        return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]
