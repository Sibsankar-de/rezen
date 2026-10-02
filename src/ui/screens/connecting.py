import asyncio
from typing import Optional
from textual import work
from textual.app import ComposeResult
from textual.containers import Center, Middle, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, LoadingIndicator

from container import container
from models.device import Device
from models.connection import Connection, ConnectionState
from services.connection_service import ConnectionService
from services.device_service import DeviceService
from services.discovery_service import DiscoveryService
from services.screen_cast_service import ScreenCastService
from utils.logger import get_logger
from .connected import ConnectedScreen
from ..layout import BaseLayout

logger = get_logger(__name__)


class ConnectingScreen(Screen):
    """Screen displayed while initiating a connection to a discovered device."""

    def __init__(
        self,
        device: Device,
        discovery_service: Optional[DiscoveryService] = None,
        connection_service: Optional[ConnectionService] = None,
        device_service: Optional[DeviceService] = None,
        screen_cast_service: Optional[ScreenCastService] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._device = device
        self._discovery_service = discovery_service
        self._connection_service = connection_service or container.connection_service
        self._device_service = device_service or container.device_service
        self._screen_cast_service = screen_cast_service or container.screen_cast_service
        self._connection: Connection | None = None

    def compose(self) -> ComposeResult:
        with BaseLayout():
            with Center():
                with Middle():
                    with Vertical(id="connecting-card"):
                        yield Label("🔗 Connecting", id="connecting-title")
                        yield Label(
                            f"Connecting to {self._device.name} ({self._device.id})",
                            id="connecting-subtitle",
                        )
                        yield Label(
                            f"IP: {self._device.ip}:{self._device.port}  |  OS: {self._device.os}",
                            id="connecting-info",
                        )
                        yield LoadingIndicator(id="connecting-spinner")
                        yield Label("", id="connecting-status")
                        yield Button("Cancel", id="btn-cancel", variant="error")

    async def on_mount(self) -> None:
        """Initiate the connection request once the screen is mounted."""
        logger.info(f"ConnectingScreen mounted for device {self._device.name} ({self._device.ip})")
        self._connect()

    @work(exclusive=True, thread=False)
    async def _connect(self) -> None:
        """Send connection request and await acceptance."""
        self._set_status("Sending connection request…")
        try:
            await self._connection_service.request_connection(self._device)
            logger.info(f"Connection request sent to {self._device.name}; awaiting acceptance.")
            self._set_status(
                f"Waiting for {self._device.name} to accept…"
            )

            # Poll for connection
            timeout = 30.0
            interval = 0.5
            start_time = asyncio.get_running_loop().time()
            connection = None

            while (asyncio.get_running_loop().time() - start_time) < timeout:
                connection = await self._connection_service.get_connection(self._device)
                if connection is not None and connection.state == ConnectionState.CONNECTED:
                    break
                await asyncio.sleep(interval)

            if connection is not None and connection.state == ConnectionState.CONNECTED:
                await self._connection_service.complete_connection(connection)
                self._connection = connection
                logger.info(f"Connected to {self._device.name} successfully (id: {connection.id}).")
                self._set_status(f"✅ Connected to {self._device.name}!")
                self._show_connected()

                # Stop discovery now that connection is established
                ds = self._discovery_service or container.discovery_service()
                if ds is not None:
                    try:
                        logger.info("Stopping discovery upon successful connection.")
                        await ds.stop_discovery()
                    except Exception as exc:
                        logger.warning(f"Error stopping discovery: {exc}")

                # The device which discovered will be the receiver:
                logger.info("Starting screen cast receiving as discovered receiver...")
                try:
                    await asyncio.wait_for(
                        self._screen_cast_service.start_receiving(),
                        timeout=5.0,
                    )
                except Exception as exc:
                    logger.warning(
                        f"Screen cast receiving startup delayed or error: {exc}",
                        exc_info=True,
                    )

                self.app.switch_screen(
                    ConnectedScreen(
                        device=self._device,
                        connection=connection,
                        connection_service=self._connection_service,
                        device_service=self._device_service,
                        screen_cast_service=self._screen_cast_service,
                        is_streamer=False,
                    )
                )
            else:
                self._set_status(f"❌ Connection to {self._device.name} timed out.")
                self._show_cancel_only()

        except Exception as exc:
            logger.error(f"Failed to connect to {self._device.name}: {exc}", exc_info=True)
            self._set_status(f"❌ Failed to connect: {exc}")
            self._show_cancel_only()

    def _set_status(self, text: str) -> None:
        try:
            self.query_one("#connecting-status", Label).update(text)
        except Exception:
            pass

    def _show_connected(self) -> None:
        """Update UI state when connected successfully."""
        try:
            self.query_one("#connecting-spinner", LoadingIndicator).display = False
        except Exception:
            pass
        try:
            btn = self.query_one("#btn-cancel", Button)
            btn.label = "Disconnect"
            btn.variant = "error"
        except Exception:
            pass

    def _show_cancel_only(self) -> None:
        """Hide spinner after a terminal error."""
        try:
            self.query_one("#connecting-spinner", LoadingIndicator).display = False
        except Exception:
            pass

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id in ("btn-cancel", "btn-disconnect"):
            if self._connection is not None:
                logger.info(
                    f"Disconnecting connection {self._connection.id} with {self._device.name}"
                )
                try:
                    await self._screen_cast_service.stop_receiving()
                except Exception:
                    pass
                try:
                    await self._connection_service.close_connection(self._connection.id)
                except Exception as exc:
                    logger.error(
                        f"Error closing connection {self._connection.id}: {exc}",
                        exc_info=True,
                    )
            self.app.pop_screen()


