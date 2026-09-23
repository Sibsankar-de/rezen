import time
from textual import work
from textual.app import ComposeResult
from textual.containers import Center, Horizontal, Middle, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Label, ListItem, ListView

from models.device import Device
from protocol.protocol import RLP
from services.discovery_service import DiscoveryService
from ..layout import BaseLayout


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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.discovery_service = DiscoveryService()
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
        await self.discovery_service.start_discovery(self._on_device_discovered)
        self._set_status("Listening for devices on network...")
        self._scan_timer = self.set_interval(1.0, self._prune_expired_devices)

    async def on_unmount(self) -> None:
        """Stop continuous discovery and pruning timer upon leaving the screen."""
        if self._scan_timer:
            self._scan_timer.stop()
            self._scan_timer = None
        await self.discovery_service.stop_discovery()

    def _on_device_discovered(self, device: Device) -> None:
        """Handle newly discovered or refreshed device packet in real time."""
        self._devices_cache[device.id] = (device, time.time())
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

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-scan":
            self._devices_cache.clear()
            self._refresh_device_list()
            self._set_status("Listening for devices on network...")
        elif event.button.id == "btn-back":
            self.app.pop_screen()
