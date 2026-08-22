import signal
import sys
import time

from rich.console import Console
from rich.table import Table

from services.device_service import DeviceService
from services.discovery_service import DiscoveryService
from utils.logger import get_logger

logger = get_logger(__name__)
console = Console()


def run_cli_discover(timeout: float = 2.0, interval: float = 3.0) -> None:
    """Run LAN discovery in headless CLI mode. Continuously and periodically scans until stopped."""
    discovery_service = DiscoveryService()
    current_device = DeviceService().get_current_device()

    logger.info(
        f"Initiating network discovery from {current_device.name} ({current_device.ip}:{current_device.port})..."
    )

    def perform_scan():
        logger.info(f"Scanning local network (timeout={timeout}s)...")
        devices = discovery_service.discover_devices(timeout=timeout)

        if not devices:
            logger.info("No active Rezen devices discovered on the network.")
            return

        table = Table(
            title=f"🔍 Discovered Rezen Devices ({len(devices)} found)",
            border_style="green",
        )
        table.add_column("Device ID", style="bold cyan")
        table.add_column("Name", style="white")
        table.add_column("Hostname", style="white")
        table.add_column("IP Address", style="yellow")
        table.add_column("Port", style="magenta")
        table.add_column("OS", style="blue")

        for dev in devices:
            table.add_row(dev.id, dev.name, dev.hostname, dev.ip, str(dev.port), dev.os)

        console.print(table)

    logger.info(
        f"Continuous discovery active (rescan every {interval}s). Press Ctrl+C to stop."
    )

    def handle_sigint(signum, frame):
        logger.info("Received interrupt signal. Discovery scan stopped cleanly.")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    try:
        while True:
            perform_scan()
            time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("Discovery scan stopped cleanly.")


