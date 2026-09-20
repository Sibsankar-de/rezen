import asyncio
import signal
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from services.broadcast_service import BroadcastService
from services.device_service import DeviceService
from utils.logger import get_logger

logger = get_logger(__name__)
console = Console()


async def run_cli_broadcast(
    interval: float = 2.0,
    stop_event: Optional[asyncio.Event] = None,
) -> None:
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
    await broadcast_service.start_private_broadcast()
    await broadcast_service.broadcast()

    logger.info(
        "Presence broadcast is active. Listening for discover requests. Press Ctrl+C to stop."
    )

    if stop_event is None:
        stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()

    def handle_signal():
        logger.info("Received interrupt signal. Stopping broadcast service...")
        stop_event.set()

    try:
        loop.add_signal_handler(signal.SIGINT, handle_signal)
        loop.add_signal_handler(signal.SIGTERM, handle_signal)
    except (NotImplementedError, RuntimeError):
        pass

    try:
        await stop_event.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await broadcast_service.stop_private_broadcast()
        logger.info("Broadcaster stopped cleanly.")
