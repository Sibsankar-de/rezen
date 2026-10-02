import asyncio
from typing import Optional
from textual import work
from textual.app import ComposeResult
from textual.containers import Center, Middle, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Label, ListItem, ListView

from container import container
from models.device import Device
from services.broadcast_service import BroadcastService
from services.connection_service import ConnectionService
from services.device_service import DeviceService
from services.screen_cast_service import ScreenCastService
from utils.logger import get_logger
from .connected import ConnectedScreen
from ..layout import BaseLayout

logger = get_logger(__name__)


class RequestListItem(ListItem):
    """ListItem representing an incoming connection request."""

    def __init__(self, device: Device, **kwargs):
        super().__init__(**kwargs)
        self.device = device

    def compose(self) -> ComposeResult:
        yield Label(
            f"📲  {self.device.name} ({self.device.id})", classes="request-item-title"
        )
        yield Label(
            f"IP: {self.device.ip}:{self.device.port}  |  OS: {self.device.os}",
            classes="request-item-subtitle",
        )


class BroadcastScreen(Screen):
    """Screen displayed while broadcasting device presence across the LAN."""

    def __init__(
        self,
        broadcast_service: BroadcastService,
        connection_service: ConnectionService,
        device_service: Optional[DeviceService] = None,
        screen_cast_service: Optional[ScreenCastService] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._broadcast_service = broadcast_service
        self._connection_service = connection_service
        self._device_service = device_service or container.device_service
        self._screen_cast_service = screen_cast_service or container.screen_cast_service
        self._pending_requests: dict[str, Device] = {}

    def compose(self) -> ComposeResult:
        device = self._connection_service.device
        with BaseLayout():
            with Center():
                with Middle():
                    with Vertical(id="broadcast-card"):
                        yield Label("📡 Broadcasting", id="broadcast-title")
                        yield Label(
                            "Your device presence is being broadcasted on the local network.",
                            id="broadcast-subtitle",
                        )
                        yield Label(
                            f"Device ID: {device.id}  |  IP: {device.ip}  |  Port: {device.port}",
                            id="broadcast-info",
                        )
                        yield Label(
                            "Incoming connection requests:",
                            id="broadcast-requests-label",
                        )
                        with VerticalScroll(id="request-list-container"):
                            yield ListView(id="request-list-view")
                        yield Label("", id="broadcast-status")
                        yield Button("Back to Home", id="btn-back", variant="primary")

    async def on_mount(self) -> None:
        """Start local network broadcast upon entering the screen."""
        logger.info("BroadcastScreen mounted, starting presence broadcast.")
        try:
            await self._broadcast_service.start_private_broadcast(
                on_connection_request=self._on_connection_request
            )
            await self._broadcast_service.broadcast()
        except Exception:
            logger.error("Failed to start broadcast service.", exc_info=True)

    async def on_unmount(self) -> None:
        """Stop local network broadcast upon leaving the screen."""
        logger.info("BroadcastScreen unmounting, stopping presence broadcast.")
        await self._broadcast_service.stop_private_broadcast()

    def _on_connection_request(self, device: Device) -> None:
        """Called by BroadcastService when a CONNECTION_REQUEST packet arrives."""
        if device.id not in self._pending_requests:
            logger.info(f"Incoming connection request from {device.name} ({device.ip}:{device.port})")
            self._pending_requests[device.id] = device
            # Schedule the UI refresh on Textual's event loop — the UDP datagram
            # callback runs synchronously inside asyncio but outside Textual's
            # message pump, so direct widget mutation must be deferred.
            self.call_later(self._refresh_request_list)

    def _refresh_request_list(self) -> None:
        """Refresh the incoming request ListView."""
        list_view = self.query_one("#request-list-view", ListView)
        list_view.clear()
        for device in self._pending_requests.values():
            list_view.append(RequestListItem(device))

        if self._pending_requests:
            self._set_status(
                f"⚠️  {len(self._pending_requests)} pending request(s). Click to accept."
            )
        else:
            self._set_status("")

    def _set_status(self, text: str) -> None:
        try:
            self.query_one("#broadcast-status", Label).update(text)
        except Exception:
            pass

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Accept the connection request when the user clicks on a pending request."""
        if isinstance(event.item, RequestListItem):
            device = event.item.device
            self._pending_requests.pop(device.id, None)
            self._refresh_request_list()
            self._accept_connection(device)

    @work(exclusive=False, thread=False)
    async def _accept_connection(self, device: Device) -> None:
        """Accept the incoming connection request asynchronously."""
        logger.info(f"User accepted connection request from {device.name} ({device.ip})")
        self._set_status(f"🔗 Accepting connection from {device.name}…")
        try:
            connection = await self._connection_service.accept_connection(device)
            logger.info(f"Connection accepted successfully: id={connection.id} with {device.name}")
            self._set_status(
                f"✅ Connected to {device.name} (connection id: {connection.id})"
            )
            logger.info("Starting screen cast streaming as broadcaster...")
            try:
                await asyncio.wait_for(
                    self._screen_cast_service.start_streaming(),
                    timeout=5.0,
                )
            except Exception as exc:
                logger.warning(
                    f"Screen cast streaming startup delayed or error: {exc}",
                    exc_info=True,
                )

            self.app.push_screen(
                ConnectedScreen(
                    device=device,
                    connection=connection,
                    connection_service=self._connection_service,
                    device_service=self._device_service,
                    screen_cast_service=self._screen_cast_service,
                    is_streamer=True,
                )
            )
        except Exception as exc:
            logger.error(f"Failed to accept connection from {device.name}: {exc}", exc_info=True)
            self._set_status(f"❌ Failed to accept connection from {device.name}: {exc}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
