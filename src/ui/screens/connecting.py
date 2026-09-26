from textual import work
from textual.app import ComposeResult
from textual.containers import Center, Middle, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, LoadingIndicator

from container import container
from models.device import Device
from models.connection import Connection
from utils.logger import get_logger
from ..layout import BaseLayout

logger = get_logger(__name__)


class ConnectingScreen(Screen):
    """Screen displayed while initiating a connection to a discovered device."""

    def __init__(self, device: Device, **kwargs):
        super().__init__(**kwargs)
        self._device = device
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
            await container.connection_service.request_connection(self._device)
            logger.info(f"Connection request sent to {self._device.name}; awaiting acceptance.")
            self._set_status(
                f"✅ Request sent. Waiting for {self._device.name} to accept…"
            )
        except Exception as exc:
            logger.error(f"Failed to connect to {self._device.name}: {exc}", exc_info=True)
            self._set_status(f"❌ Failed to connect: {exc}")
            self._show_cancel_only()

    def _set_status(self, text: str) -> None:
        try:
            self.query_one("#connecting-status", Label).update(text)
        except Exception:
            pass

    def _show_cancel_only(self) -> None:
        """Hide spinner after a terminal error."""
        try:
            self.query_one("#connecting-spinner", LoadingIndicator).display = False
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.app.pop_screen()
