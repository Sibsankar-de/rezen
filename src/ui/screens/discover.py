import asyncio
from textual import work
from textual.app import ComposeResult
from textual.containers import Center, Horizontal, Middle, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Label, ListItem, ListView

from models.device import Device
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
        self._discovered_devices: list[Device] = []
        self._scan_timer = None

    def compose(self) -> ComposeResult:
        with BaseLayout():
            with Center():
                with Middle():
                    with Vertical(id="discover-card"):
                        yield Label("🔍 Discovered Devices", id="discover-title")
                        yield Label(
                            "Scanning local network for active Rezen devices (auto-rescans every 10s)...",
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

    def on_mount(self) -> None:
        """Trigger initial device scan and schedule periodic rescan every 10 seconds."""
        self.run_scan()
        self._scan_timer = self.set_interval(10.0, self.run_scan)

    def on_unmount(self) -> None:
        """Stop periodic rescan timer when screen is unmounted."""
        if self._scan_timer:
            self._scan_timer.stop()
            self._scan_timer = None

    @work(exclusive=True, thread=True)
    def run_scan(self) -> None:
        """Perform network device discovery in a background worker thread."""
        self.app.call_from_thread(self._set_status, "Scanning network for devices...")
        try:
            devices = self.discovery_service.discover_devices(timeout=1.5)
            self._discovered_devices = devices
            self.app.call_from_thread(self._update_device_list, devices)
        except Exception as err:
            self.app.call_from_thread(self._set_status, f"Error scanning: {err}")

    def _set_status(self, status_text: str) -> None:
        status_label = self.query_one("#scan-status", Label)
        status_label.update(status_text)

    def _update_device_list(self, devices: list[Device]) -> None:
        list_view = self.query_one("#device-list-view", ListView)
        list_view.clear()

        if not devices:
            self._set_status("No devices discovered on network.")
        else:
            self._set_status(f"Found {len(devices)} device(s) on network.")
            for dev in devices:
                list_view.append(DeviceListItem(dev))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-scan":
            self.run_scan()
        elif event.button.id == "btn-back":
            self.app.pop_screen()
