import asyncio
import signal
from typing import Optional

from rich.console import Console
from rich.table import Table

from services.device_service import DeviceService
from services.discovery_service import DiscoveryService
from utils.logger import get_logger

logger = get_logger(__name__)
console = Console()


async def run_cli_discover(
    timeout: float = 2.0,
    interval: float = 3.0,
    stop_event: Optional[asyncio.Event] = None,
) -> None:
    """Run LAN discovery in headless CLI mode. Continuously and periodically scans until stopped."""
    discovery_service = DiscoveryService()
    current_device = DeviceService().get_current_device()

    logger.info(
        f"Initiating network discovery from {current_device.name} ({current_device.ip}:{current_device.port})..."
    )

    async def perform_scan() -> None:
        logger.info(f"Scanning local network (timeout={timeout}s)...")
        devices = await discovery_service.discover_devices(timeout=timeout)

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

    if stop_event is None:
        stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()

    def handle_signal():
        logger.info("Received interrupt signal. Discovery scan stopped cleanly.")
        stop_event.set()

    try:
        loop.add_signal_handler(signal.SIGINT, handle_signal)
        loop.add_signal_handler(signal.SIGTERM, handle_signal)
    except (NotImplementedError, RuntimeError):
        pass

    async def scan_loop() -> None:
        while not stop_event.is_set():
            await perform_scan()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    scan_task = asyncio.create_task(scan_loop())
    try:
        await stop_event.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        scan_task.cancel()
        try:
            await scan_task
        except asyncio.CancelledError:
            pass

    logger.info("Discovery scan stopped cleanly.")
