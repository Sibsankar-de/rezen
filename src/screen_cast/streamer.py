import asyncio
import time
from typing import Optional, Callable, Awaitable, Any

import numpy as np

from screen_cast.capture import FrameSource, create_capture
from screen_cast.h264 import H264Encoder
from models.stream_chunk import StreamChunk, ChunkType, FlagType

from settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

TARGET_FPS = 30
STATS_INTERVAL_SECONDS = 5.0


class Streamer:
    """Handle streaming of screen"""

    def __init__(
        self,
        capture: Optional[FrameSource] = None,
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
        self._captured_frames = 0
        self._encoded_frames = 0
        self._sent_chunks = 0
        self._sent_bytes = 0
        self._stats_started_at: float | None = None
        self._capture_error: Exception | None = None

    @property
    def capture_error(self) -> Exception | None:
        """The error that killed the capture loop, if any."""
        return self._capture_error

    @property
    def capture_warning(self) -> str | None:
        """Non-fatal capture health hint, e.g. a backend stuck on black frames."""
        if self._capture_error is not None:
            return str(self._capture_error)
        if self._capture is None:
            return None
        try:
            return self._capture.warning
        except Exception:
            return None

    @property
    def capture(self) -> FrameSource:
        if self._capture is None:
            self._capture = create_capture(target_fps=TARGET_FPS)
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

        logger.info(
            f"Streamer started: capturing {self.capture.width}x{self.capture.height} "
            f"at {TARGET_FPS} fps, chunk size {settings.STREAM_CHUNK_SIZE} bytes."
        )

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
        target_fps = TARGET_FPS
        frame_interval = 1.0 / target_fps

        while self._running:
            loop_start = asyncio.get_running_loop().time()
            try:
                frame = await asyncio.to_thread(self.capture.capture)
                self._captured_frames += 1
                if self._captured_frames == 1:
                    logger.info(
                        f"First frame captured: shape={frame.shape} dtype={frame.dtype}."
                    )
                if self._frame_queue.full():
                    try:
                        self._frame_queue.get_nowait()
                        self._frame_queue.task_done()
                    except (asyncio.QueueEmpty, ValueError):
                        pass
                await self._frame_queue.put(frame)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._capture_error = exc
                logger.error(f"Error in screen capture loop: {exc}", exc_info=True)
                break

            elapsed = asyncio.get_running_loop().time() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                try:
                    await asyncio.sleep(sleep_time)
                except asyncio.CancelledError:
                    break

        logger.info(
            f"Capture loop stopped after {self._captured_frames} frame(s); "
            f"queue depth {self._frame_queue.qsize()}."
        )

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
                break
            except Exception:
                logger.error("Error in screen encode loop", exc_info=True)
            finally:
                self._frame_queue.task_done()

            self._log_stats()

            if self._capture_task is not None and self._capture_task.done():
                logger.error(
                    "Capture loop is no longer producing frames; stopping the encode loop."
                )
                break

        logger.info(f"Encode loop stopped after {self._encoded_frames} encoded frame(s).")

    def _log_stats(self) -> None:
        """Emit a periodic summary of the streaming pipeline."""
        now = time.monotonic()
        if self._stats_started_at is None:
            self._stats_started_at = now
            return
        elapsed = now - self._stats_started_at
        if elapsed < STATS_INTERVAL_SECONDS:
            return

        self._stats_started_at = now
        logger.info(
            f"Stream stats: captured={self._captured_frames} "
            f"encoded={self._encoded_frames} "
            f"chunks_sent={self._sent_chunks} "
            f"bytes_sent={self._sent_bytes} "
            f"queue_depth={self._frame_queue.qsize()} "
            f"elapsed={elapsed:.1f}s"
        )

    async def _encode_and_send_chunk(self, frame: np.ndarray):
        """Encode frame, create chunks and send chunks"""
        packets = await asyncio.to_thread(self.encoder.encode, frame)
        self._encoded_frames += 1

        for packet in packets:
            chunks = self._create_chunks(packet.data, settings.STREAM_CHUNK_SIZE)

            for chunk_index, data in enumerate(chunks):
                if chunk_index == len(chunks) - 1:
                    chunk_flag = FlagType.END_CHUNK
                elif chunk_index == 0:
                    chunk_flag = FlagType.START_CHUNK
                else:
                    chunk_flag = FlagType.MEDIATE_CHUNK

                stream_chunk = StreamChunk(
                    frame_id=f"frame_{self._frame_index}",
                    chunk_id=f"chunk_{chunk_index}",
                    data=data,
                    size=len(data),
                    total_chunks=len(chunks),
                    type=ChunkType.VIDEO,
                    flag=chunk_flag,
                )

                # send the chunk
                await self._send(stream_chunk)
                self._sent_chunks += 1
                self._sent_bytes += len(data)

            logger.debug(
                f"Encoded frame {self._frame_index}: {len(packet.data)} bytes in "
                f"{len(chunks)} chunk(s), keyframe={packet.is_keyframe}."
            )

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
