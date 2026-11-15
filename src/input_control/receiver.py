import asyncio
import logging
from collections.abc import Callable

from input_control.keyboard_controller import KeyboardController
from input_control.mouse_controller import MouseController
from input_control.pointer_overlay import PointerOverlay
from models.input import InputObject, InputType
from settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class InputReceiver:
    """Receive streamed inputs"""

    def __init__(
        self,
        pointer_overlay: PointerOverlay | None = None,
        on_remote_pointer: Callable[[int, int, bool], None] | None = None,
    ):
        self._keyboard_controller = KeyboardController()
        self._mouse_controller = MouseController()
        self._mouse_controller.set_virtual_mode(True)
        self._pointer_overlay = pointer_overlay
        self._on_remote_pointer = on_remote_pointer
        self._last_remote_x: int | None = None
        self._last_remote_y: int | None = None
        self._remote_mouse_down = False
        self._host_screen_size: tuple[int, int] | None = None

        self._running = False
        self._receive_queue: asyncio.Queue[InputObject] = asyncio.Queue(
            maxsize=settings.INPUT_RECEIVE_QUEUE_MAX_SIZE
        )

        self._receive_task: asyncio.Task | None = None

    def set_pointer_callback(
        self, cb: Callable[[int, int, bool], None] | None
    ) -> None:
        """Set callback to notify screen cast streamer of remote pointer position."""
        self._on_remote_pointer = cb

    def _get_host_screen_size(self) -> tuple[int, int]:
        if self._host_screen_size is None:
            from screen_cast.capture import get_system_screen_size

            self._host_screen_size = get_system_screen_size()
        return self._host_screen_size

    async def start(self) -> None:
        """The receiver with receive loop"""
        if self._running:
            logger.info("InputReceiver already running.")
            return

        self._running = True
        if self._pointer_overlay is None:
            self._pointer_overlay = PointerOverlay()
        self._pointer_overlay.start()

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

        if self._pointer_overlay is not None:
            self._pointer_overlay.stop()
            self._pointer_overlay = None

        await self._clear_queue()
        self._keyboard_controller.close()
        self._mouse_controller.close()
        logger.info("InputReceiver stopped.")

    async def receive_input(self, input_object: InputObject) -> None:
        """Enqueue the received event"""
        logger.info(
            f"[RECEIVER] Enqueuing received input: {input_object.data} "
            f"(queue size before put: {self._receive_queue.qsize()})"
        )
        await self._receive_queue.put(input_object)

    async def _run_receive_loop(self) -> None:
        """Listen queue and perform operation with move event coalescing."""
        logger.info("[RECEIVER] Receive loop started.")
        while self._running:
            try:
                event = await self._receive_queue.get()
            except asyncio.CancelledError:
                break

            try:
                # Coalesce consecutive move_abs events to eliminate lag
                while not self._receive_queue.empty():
                    try:
                        peek = self._receive_queue.get_nowait()
                        if (
                            event.type == InputType.MOUSE
                            and peek.type == InputType.MOUSE
                            and any(d.startswith("move_abs:") for d in event.data)
                            and any(d.startswith("move_abs:") for d in peek.data)
                        ):
                            self._receive_queue.task_done()
                            event = peek
                        else:
                            self._receive_queue.task_done()
                            await self._handle_received_event(event)
                            event = peek
                            break
                    except (asyncio.QueueEmpty, ValueError):
                        break

                await self._handle_received_event(event)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Failed to process in receive loop")
            finally:
                self._receive_queue.task_done()
        logger.info("[RECEIVER] Receive loop stopped.")

    async def _handle_received_event(self, event: InputObject) -> None:
        """Handle the received input event with exact coordinate calibration."""
        match event.type:
            case InputType.KEYBOARD:
                self._keyboard_controller.apply(event)
            case InputType.MOUSE:
                for encoded in event.data:
                    if encoded.startswith("move_abs:"):
                        payload = encoded[9:]
                        coords, _, norm_part = payload.partition(":")
                        x_str, _, y_str = coords.partition(",")
                        try:
                            hx = int(x_str)
                            hy = int(y_str)
                            if norm_part:
                                nx_str, _, ny_str = norm_part.partition(",")
                                nx = float(nx_str)
                                ny = float(ny_str)
                                host_w, host_h = self._get_host_screen_size()
                                calibrated_x = max(0, min(host_w - 1, round(nx * host_w)))
                                calibrated_y = max(0, min(host_h - 1, round(ny * host_h)))
                            else:
                                calibrated_x = hx
                                calibrated_y = hy

                            self._last_remote_x = calibrated_x
                            self._last_remote_y = calibrated_y

                            if self._pointer_overlay is not None:
                                self._pointer_overlay.update_position(
                                    calibrated_x, calibrated_y
                                )
                            if self._on_remote_pointer is not None:
                                self._on_remote_pointer(
                                    calibrated_x, calibrated_y, self._remote_mouse_down
                                )
                        except (ValueError, TypeError):
                            pass

                    elif encoded.startswith("click:"):
                        parts = encoded.split(":")
                        btn = parts[1] if len(parts) > 1 else "left"
                        pressed = parts[2] == "1" if len(parts) > 2 else False
                        self._remote_mouse_down = pressed

                        # If click payload includes coordinates: click:btn:state:hx,hy:nx,ny
                        if len(parts) >= 4:
                            try:
                                coords = parts[3]
                                x_str, _, y_str = coords.partition(",")
                                hx = int(x_str)
                                hy = int(y_str)
                                if len(parts) >= 5 and parts[4]:
                                    nx_str, _, ny_str = parts[4].partition(",")
                                    nx = float(nx_str)
                                    ny = float(ny_str)
                                    host_w, host_h = self._get_host_screen_size()
                                    calibrated_x = max(0, min(host_w - 1, round(nx * host_w)))
                                    calibrated_y = max(0, min(host_h - 1, round(ny * host_h)))
                                else:
                                    calibrated_x = hx
                                    calibrated_y = hy
                                self._last_remote_x = calibrated_x
                                self._last_remote_y = calibrated_y
                            except (ValueError, TypeError):
                                pass

                        if self._pointer_overlay is not None:
                            self._pointer_overlay.show_click_feedback(btn, pressed)
                        if (
                            self._on_remote_pointer is not None
                            and self._last_remote_x is not None
                            and self._last_remote_y is not None
                        ):
                            self._on_remote_pointer(
                                self._last_remote_x, self._last_remote_y, pressed
                            )

                self._mouse_controller.apply(event)
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
