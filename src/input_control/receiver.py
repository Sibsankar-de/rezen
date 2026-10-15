import asyncio

from input_control.keyboard_controller import KeyboardController
from models.input import InputObject, InputType
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
            logger.info("InputReceiver already running.")
            return

        self._running = True
        self._receive_task = asyncio.create_task(self._run_receive_loop())
        logger.info("InputReceiver started.")

    async def stop(self) -> None:
        """Stop the receiver"""
        if not self._running:
            return

        logger.info("Stopping InputReceiver...")
        self._running = False

        if self._receive_task is not None:
            self._receive_task.cancel()
            await asyncio.gather(self._receive_task, return_exceptions=True)
            self._receive_task = None

        await self._clear_queue()
        logger.info("InputReceiver stopped.")

    async def receive_input(self, input_object: InputObject) -> None:
        """Enqueue the received event"""
        logger.info(
            f"[RECEIVER] Enqueuing received input: {input_object.data} "
            f"(queue size before put: {self._receive_queue.qsize()})"
        )
        await self._receive_queue.put(input_object)

    async def _run_receive_loop(self) -> None:
        """Listen queue and perform operation"""
        logger.info("[RECEIVER] Receive loop started.")
        while self._running:
            try:
                event = await self._receive_queue.get()
            except asyncio.CancelledError:
                break

            try:
                logger.info(
                    f"[RECEIVER] Dequeued input event: type={event.type}, data={event.data}"
                )
                await self._handle_received_event(event)
                logger.info(f"[RECEIVER] Finished processing event: {event.data}")
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Failed to process in receive loop")
            finally:
                self._receive_queue.task_done()
        logger.info("[RECEIVER] Receive loop stopped.")

    async def _handle_received_event(self, event: InputObject) -> None:
        """Handle the received input event"""
        match event.type:
            case InputType.KEYBOARD:
                self._keyboard_controller.apply(event)
            case _:
                logger.warning(f"[RECEIVER] Unhandled input event type: {event.type}")

    async def _clear_queue(self) -> None:
        """Removes all elements from the queue"""
        while not self._receive_queue.empty():
            try:
                self._receive_queue.get_nowait()
                self._receive_queue.task_done()
            except (asyncio.QueueEmpty, ValueError):
                break
