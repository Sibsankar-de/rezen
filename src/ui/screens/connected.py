from typing import Optional
from textual.app import ComposeResult
from textual.containers import Center, Middle, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label

from container import container
from models.device import Device
from models.connection import Connection
from services.connection_service import ConnectionService
from services.device_service import DeviceService
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
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._device = device
        self._connection = connection
        self._connection_service = connection_service or container.connection_service
        self._device_service = device_service or container.device_service

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
                        yield Label(
                            f"Status: Active (id: {self._connection.id})",
                            id="connected-status",
                        )
                        yield Button("Disconnect", id="btn-disconnect", variant="error")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-disconnect":
            logger.info(
                f"Disconnect requested for {self._device.name} (id: {self._connection.id})"
            )
            try:
                await self._connection_service.close_connection(self._connection.id)
            except Exception as exc:
                logger.error(
                    f"Error closing connection {self._connection.id}: {exc}",
                    exc_info=True,
                )
            self.app.pop_screen()
