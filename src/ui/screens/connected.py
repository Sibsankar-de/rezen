from typing import Optional
from textual.app import ComposeResult
from textual.containers import Center, Middle, Vertical
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Button, Label

from container import container
from models.device import Device
from models.connection import Connection
from services.connection_service import ConnectionService
from services.device_service import DeviceService
from services.screen_cast_service import ScreenCastService
from utils.logger import get_logger
from ..layout import BaseLayout

logger = get_logger(__name__)


class ConnectedScreen(Screen):
    """Screen displayed when a device is actively connected."""

    def __init__(
        self,
        device: Device,
        connection: Connection,
        connection_service: Optional[ConnectionService] = None,
        device_service: Optional[DeviceService] = None,
        screen_cast_service: Optional[ScreenCastService] = None,
        is_streamer: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._device = device
        self._connection = connection
        self._connection_service = connection_service or container.connection_service
        self._device_service = device_service or container.device_service
        self._screen_cast_service = screen_cast_service or container.screen_cast_service
        self._is_streamer = is_streamer
        self._stopped = False
        self._health_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        with BaseLayout():
            with Center():
                with Middle():
                    with Vertical(id="connected-card"):
                        yield Label("🔗 Connected", id="connected-title")
                        yield Label(
                            f"Connected to {self._device.name} ({self._device.id})",
                            id="connected-subtitle",
                        )
                        yield Label(
                            f"IP: {self._device.ip}:{self._device.port}  |  OS: {self._device.os}",
                            id="connected-info",
                        )
                        role_text = "Streaming screen" if self._is_streamer else "Receiving screen"
                        yield Label(
                            f"Status: Active ({role_text}) (id: {self._connection.id})",
                            id="connected-status",
                        )
                        yield Button("Disconnect", id="btn-disconnect", variant="error")

    def on_mount(self) -> None:
        """Poll the streaming pipeline health while connected."""
        self._health_timer = self.set_interval(2.0, self._check_health)

    def _check_health(self) -> None:
        """Surface streamer failures (e.g. an unreadable framebuffer) in the UI."""
        if self._stopped or not self._is_streamer:
            return

        streamer = self._screen_cast_service.streamer
        error = streamer.capture_error
        if error is None:
            return

        try:
            self.query_one("#connected-status", Label).update(
                f"Status: Capture failed - {error}"
            )
        except Exception:
            pass

    async def _stop_screen_cast(self) -> None:
        """Stop streaming or receiving if not already stopped."""
        if self._stopped:
            return
        self._stopped = True
        try:
            if self._is_streamer:
                await self._screen_cast_service.stop_streaming()
            else:
                await self._screen_cast_service.stop_receiving()
        except Exception as exc:
            logger.error(
                f"Error stopping screen cast service: {exc}",
                exc_info=True,
            )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-disconnect":
            logger.info(
                f"Disconnect requested for {self._device.name} (id: {self._connection.id})"
            )
            await self._stop_screen_cast()
            try:
                await self._connection_service.close_connection(self._connection.id)
            except Exception as exc:
                logger.error(
                    f"Error closing connection {self._connection.id}: {exc}",
                    exc_info=True,
                )
            self.app.pop_screen()

    async def on_unmount(self) -> None:
        await self._stop_screen_cast()
