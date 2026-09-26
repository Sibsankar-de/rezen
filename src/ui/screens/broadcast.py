from textual import work
from textual.app import ComposeResult
from textual.containers import Center, Middle, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Label, ListItem, ListView

from models.device import Device
from services.broadcast_service import BroadcastService
from services.connection_service import ConnectionService
from services.device_service import DeviceService
from ..layout import BaseLayout


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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.broadcast_service: BroadcastService | None = None
        self._connection_service = ConnectionService()
        self._pending_requests: dict[str, Device] = {}

    def compose(self) -> ComposeResult:
        device = DeviceService().get_current_device()
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
        self.broadcast_service = BroadcastService()
        await self.broadcast_service.start_private_broadcast(
            on_connection_request=self._on_connection_request
        )
        await self.broadcast_service.broadcast()

    async def on_unmount(self) -> None:
        """Stop local network broadcast upon leaving the screen."""
        if self.broadcast_service:
            await self.broadcast_service.stop_private_broadcast()
            self.broadcast_service = None

    def _on_connection_request(self, device: Device) -> None:
        """Called by BroadcastService when a CONNECTION_REQUEST packet arrives."""
        if device.id not in self._pending_requests:
            self._pending_requests[device.id] = device
            self._refresh_request_list()

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
        self._set_status(f"🔗 Accepting connection from {device.name}…")
        try:
            connection = await self._connection_service.accept_connection(device)
            self._set_status(
                f"✅ Connected to {device.name} (connection id: {connection.id})"
            )
        except Exception as exc:
            self._set_status(f"❌ Failed to accept connection from {device.name}: {exc}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()

