import asyncio

from models.input import InputObject, InputType
from input_control.keyboard_controller import KeyboardController

from settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class InputReceiver:
    """Receive streamed inputs"""

    def __init__(self):
        self._keyboard_controller = KeyboardController()

        self._running = False
        self._receive_queue: asyncio.Queue[InputObject] = asyncio.Queue(
            maxsize=settings.INPUT_RECEIVE_QUEUE_MAX_SIZE
        )

        self._receive_task: asyncio.Task | None = None

    async def start(self) -> None:
        """The receiver with receive loop"""
        if self._running:
            return

        self._running = True
        self._receive_task = asyncio.create_task(self._run_receive_loop)

    async def stop(self) -> None:
        """Stop the receiver"""
        if not self._running:
            return

        self._running = False

        if self._receive_task is not None:
            self._receive_task.cancel()
            await asyncio.gather(self._receive_task, return_exceptions=True)

        await self._clear_queue()

    async def receive_input(self, input_object: InputObject) -> None:
        """Enqueue the received event"""
        await self._receive_queue.put(input_object)

    async def _run_receive_loop(self) -> None:
        """Listen queue and perform oparation"""
        while self._running and not self._receive_queue.empty():
            try:
                event = await self._receive_queue.get()
            except asyncio.CancelledError:
                break

            try:
                await self._handle_received_event(event)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.error("Failed to process in receive loop", exc_info=True)
            finally:
                self._receive_queue.task_done()

    async def _handle_received_event(self, event: InputObject) -> None:
        """Handle the received input event"""
        match event.type:
            case InputType.KEYBOARD:
                self._keyboard_controller.apply(event)

    async def _clear_queue(self) -> None:
        """Removes all elements from the queue"""
        while not self._receive_queue.empty():
            try:
                self._receive_queue.get_nowait()
                self._receive_queue.task_done()
            except (asyncio.QueueEmpty, ValueError):
                break
