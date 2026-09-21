import asyncio
import signal
import time
from typing import Optional

from rich.console import Console
from rich.table import Table

from models.device import Device
from protocol.protocol import RLP
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
    """Run LAN discovery in headless CLI mode continuously until stopped."""
    discovery_service = DiscoveryService()
    current_device = DeviceService().get_current_device()
    devices_cache: dict[str, tuple[Device, float]] = {}

    logger.info(
        f"Initiating network discovery from {current_device.name} ({current_device.ip}:{current_device.port})..."
    )

    def print_devices() -> None:
        active_devices = [dev for dev, _ in devices_cache.values()]
        if not active_devices:
            return

        table = Table(
            title=f"🔍 Discovered Rezen Devices ({len(active_devices)} found)",
            border_style="green",
        )
        table.add_column("Device ID", style="bold cyan")
        table.add_column("Name", style="white")
        table.add_column("Hostname", style="white")
        table.add_column("IP Address", style="yellow")
        table.add_column("Port", style="magenta")
        table.add_column("OS", style="blue")

        for dev in active_devices:
            table.add_row(dev.id, dev.name, dev.hostname, dev.ip, str(dev.port), dev.os)

        console.print(table)

    def on_device_discovered(device: Device) -> None:
        is_new = device.id not in devices_cache
        devices_cache[device.id] = (device, time.time())
        if is_new:
            logger.info(f"Discovered device: {device.name} ({device.ip})")
            print_devices()

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

    await discovery_service.start_discovery(on_device_discovered)
    logger.info("Continuous discovery active. Press Ctrl+C to stop.")

    async def prune_loop() -> None:
        while not stop_event.is_set():
            now = time.time()
            cutoff = now - RLP.DEVICE_TIMEOUT
            removed = False
            for dev_id in list(devices_cache.keys()):
                if devices_cache[dev_id][1] < cutoff:
                    del devices_cache[dev_id]
                    removed = True
            if removed:
                print_devices()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass

    prune_task = asyncio.create_task(prune_loop())
    try:
        await stop_event.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        prune_task.cancel()
        try:
            await prune_task
        except asyncio.CancelledError:
            pass
        await discovery_service.stop_discovery()

    logger.info("Discovery scan stopped cleanly.")
