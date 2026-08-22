import signal
import sys
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from services.broadcast_service import BroadcastService
from services.device_service import DeviceService
from utils.logger import get_logger

logger = get_logger(__name__)
console = Console()


def run_cli_broadcast(interval: float = 2.0) -> None:
    """Run LAN presence broadcaster continuously in headless CLI mode with logging."""
    device_service = DeviceService()
    device = device_service.get_current_device()

    table = Table(title="📡 Local Device Information", border_style="cyan")
    table.add_column("Property", style="bold white")
    table.add_column("Value", style="green")
    table.add_row("Device ID", device.id)
    table.add_row("Device Name", device.name)
    table.add_row("Hostname", device.hostname)
    table.add_row("Local IP", device.ip)
    table.add_row("Broadcast Port", str(device.port))
    table.add_row("Operating System", device.os)
    table.add_row("Heartbeat Interval", f"{interval}s")

    console.print(
        Panel(
            table,
            title="[bold cyan]Rezen Headless Broadcaster[/bold cyan]",
            expand=False,
        )
    )
    logger.info(
        f"Starting broadcast service on port {device.port} (heartbeat: {interval}s)..."
    )

    broadcast_service = BroadcastService(interval=interval)
    broadcast_service.start_private_broadcast()
    broadcast_service.broadcast()

    logger.info(
        "Presence broadcast is active. Listening for discover requests. Press Ctrl+C to stop."
    )

    def handle_sigint(signum, frame):
        logger.info("Received interrupt signal. Stopping broadcast service...")
        broadcast_service.stop_private_broadcast()
        logger.info("Broadcaster stopped cleanly.")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Stopping broadcast service...")
        broadcast_service.stop_private_broadcast()
        logger.info("Broadcaster stopped cleanly.")
