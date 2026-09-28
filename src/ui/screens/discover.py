import time
from typing import Optional
from textual import work
from textual.app import ComposeResult
from textual.containers import Center, Horizontal, Middle, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Label, ListItem, ListView

from container import container
from models.device import Device
from protocol.protocol import RLP
from services.connection_service import ConnectionService
from services.device_service import DeviceService
from services.discovery_service import DiscoveryService
from utils.logger import get_logger
from .connecting import ConnectingScreen
from ..layout import BaseLayout

logger = get_logger(__name__)


class DeviceListItem(ListItem):
    """Custom ListItem representing a discovered LAN device."""

    def __init__(self, device: Device, **kwargs):
        super().__init__(**kwargs)
        self.device = device

    def compose(self) -> ComposeResult:
        yield Label(
            f"🖥  {self.device.name} ({self.device.id})", classes="device-item-title"
        )
        yield Label(
            f"IP: {self.device.ip}:{self.device.port}  |  OS: {self.device.os}  |  Host: {self.device.hostname}",
            classes="device-item-subtitle",
        )


class DiscoverScreen(Screen):
    """Screen for scanning and displaying discovered Rezen devices on the LAN."""

    def __init__(
        self,
        discovery_service: DiscoveryService,
        connection_service: Optional[ConnectionService] = None,
        device_service: Optional[DeviceService] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._discovery_service = discovery_service
        self._connection_service = connection_service or container.connection_service
        self._device_service = device_service or container.device_service
        self._devices_cache: dict[str, tuple[Device, float]] = {}
        self._scan_timer = None

    def compose(self) -> ComposeResult:
        with BaseLayout():
            with Center():
                with Middle():
                    with Vertical(id="discover-card"):
                        yield Label("🔍 Discovered Devices", id="discover-title")
                        yield Label(
                            "Continuously listening for active Rezen devices on the local network...",
                            id="discover-subtitle",
                        )

                        yield Label("Ready to scan", id="scan-status")

                        with VerticalScroll(id="device-list-container"):
                            yield ListView(id="device-list-view")

                        with Horizontal(id="discover-actions"):
                            yield Button("Scan Now", id="btn-scan", variant="success")
                            yield Button(
                                "Back to Home", id="btn-back", variant="primary"
                            )

    async def on_mount(self) -> None:
        """Start continuous discovery and periodic pruning of expired devices."""
        logger.info("DiscoverScreen mounted, starting continuous discovery.")
        try:
            await self._discovery_service.start_discovery(self._on_device_discovered)
        except Exception:
            logger.error("Failed to start discovery service.", exc_info=True)
        self._set_status("Listening for devices on network...")
        self._scan_timer = self.set_interval(1.0, self._prune_expired_devices)

    async def on_unmount(self) -> None:
        """Stop continuous discovery and pruning timer upon leaving the screen."""
        logger.info("DiscoverScreen unmounting, stopping discovery.")
        if self._scan_timer:
            self._scan_timer.stop()
            self._scan_timer = None
        await self._discovery_service.stop_discovery()

    def _on_device_discovered(self, device: Device) -> None:
        """Handle newly discovered or refreshed device packet in real time."""
        is_new = device.id not in self._devices_cache
        self._devices_cache[device.id] = (device, time.time())
        if is_new:
            logger.info(f"New device discovered: {device.name} ({device.ip}:{device.port})")
        self._refresh_device_list()

    def _prune_expired_devices(self) -> None:
        """Remove devices not seen within RLP.DEVICE_TIMEOUT seconds."""
        cutoff = time.time() - RLP.DEVICE_TIMEOUT
        expired = [
            dev_id
            for dev_id, (_, last_seen) in self._devices_cache.items()
            if last_seen < cutoff
        ]
        if expired:
            for dev_id in expired:
                del self._devices_cache[dev_id]
            logger.info(f"Pruned {len(expired)} expired device(s) from cache.")
            self._refresh_device_list()

    def _refresh_device_list(self) -> None:
        list_view = self.query_one("#device-list-view", ListView)
        list_view.clear()

        active_devices = [dev for dev, _ in self._devices_cache.values()]
        if not active_devices:
            self._set_status("No devices discovered on network.")
        else:
            self._set_status(f"Found {len(active_devices)} device(s) on network.")
            for dev in active_devices:
                list_view.append(DeviceListItem(dev))

    def _set_status(self, status_text: str) -> None:
        status_label = self.query_one("#scan-status", Label)
        status_label.update(status_text)

    @work(exclusive=True)
    async def run_scan(self) -> None:
        """Manual refresh trigger."""
        self._prune_expired_devices()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Open ConnectingScreen when the user clicks a discovered device."""
        if isinstance(event.item, DeviceListItem):
            self.app.push_screen(
                ConnectingScreen(
                    device=event.item.device,
                    connection_service=self._connection_service,
                    device_service=self._device_service,
                )
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-scan":
            self._devices_cache.clear()
            self._refresh_device_list()
            self._set_status("Listening for devices on network...")
        elif event.button.id == "btn-back":
            self.app.pop_screen()
