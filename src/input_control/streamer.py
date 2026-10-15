import asyncio
from collections.abc import Awaitable, Callable

from input_control.keyboard_capture import KeyboardCapture
from models.input import InputObject
from settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class InputStreamer:
    """Capture and stream input (keyboard and mouse)"""

    def __init__(self):
        self._running = False

        self._send_task: asyncio.Task | None = None

        self._keyboard_capture = KeyboardCapture()
        self._input_queue: asyncio.Queue[InputObject] = asyncio.Queue(
            maxsize=settings.INPUT_STREAM_QUEUE_MAX_SIZE
        )

    async def start(self, send: Callable[[InputObject], Awaitable[None]]) -> None:
        """Start the capture loop and sending loop."""
        if self._running:
            return

        self._running = True
        self._send = send

        await self._keyboard_capture.start(enqueue=self._handle_keyboard_input)
        self._send_task = asyncio.create_task(self._run_send_loop())

        logger.info("Input streamer started. Capturing input events.")

    async def stop(self) -> None:
        """Stop the streamer"""
        if not self._running:
            return

        self._running = False
        await self._keyboard_capture.stop()

        if self._send_task is not None:
            self._send_task.cancel()
            await asyncio.gather(self._send_task, return_exceptions=True)
            self._send_task = None

        await self._clear_queue()

    def _handle_keyboard_input(self, input_object: InputObject) -> None:
        """Handle keyboard on press event"""
        try:
            self._input_queue.put_nowait(input_object)
            logger.info(
                f"[STREAMER] Queued input event: {input_object.data} "
                f"(pending in queue: {self._input_queue.qsize()})"
            )
        except asyncio.QueueFull:
            logger.warning("Input stream queue full, dropping event")

    async def _run_send_loop(self) -> None:
        """Listen the queue and send the input objects"""
        logger.info("[STREAMER] Send loop started.")
        while self._running:
            try:
                input_object = await self._input_queue.get()
            except asyncio.CancelledError:
                break

            try:
                logger.info(
                    f"[STREAMER] Sending input event to network: {input_object.data}"
                )
                await self._send(input_object)
                logger.info(
                    f"[STREAMER] Successfully sent input event: {input_object.data}"
                )
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in input event send loop")
            finally:
                self._input_queue.task_done()
        logger.info("[STREAMER] Send loop stopped.")

    async def _clear_queue(self) -> None:
        """Removes all elements from the queue"""
        while not self._input_queue.empty():
            try:
                self._input_queue.get_nowait()
                self._input_queue.task_done()
            except (asyncio.QueueEmpty, ValueError):
                break
