from textual.app import ComposeResult
from textual.containers import Center, Middle, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label

from services.broadcast_service import BroadcastService
from services.device_service import DeviceService
from ..layout import BaseLayout


class BroadcastScreen(Screen):
    """Screen displayed while broadcasting device presence across the LAN."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.broadcast_service: BroadcastService | None = None

    def compose(self) -> ComposeResult:
        device = DeviceService().get_current_device()
        with BaseLayout():
            with Center():
                with Middle():
                    with Vertical(id="broadcast-card"):
                        yield Label("📡 Broadcasting", id="broadcast-title")
                        yield Label(
                            "Your device presence is currently being broadcasted on the local network.",
                            id="broadcast-subtitle",
                        )
                        yield Label(
                            f"Device ID: {device.id}  |  IP: {device.ip}  |  Port: {device.port}",
                            id="broadcast-info",
                        )
                        yield Button("Back to Home", id="btn-back", variant="primary")

    def on_mount(self) -> None:
        """Start local network broadcast upon entering the screen."""
        self.broadcast_service = BroadcastService()
        self.broadcast_service.start_private_broadcast()
        self.broadcast_service.broadcast()

    def on_unmount(self) -> None:
        """Stop local network broadcast upon leaving the screen."""
        if self.broadcast_service:
            self.broadcast_service.stop_private_broadcast()
            self.broadcast_service = None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
