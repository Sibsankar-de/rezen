import asyncio
from typing import Callable, Optional

from models.device import Device
from protocol.broadcaster import Broadcaster
from protocol.packet import Packet, PacketType
from services.device_service import DeviceService
from utils.logger import get_logger

logger = get_logger(__name__)


class DiscoveryService:
    """Service to discover Rezen devices on the local network by collecting network packets."""

    def __init__(
        self,
        broadcaster: Optional[Broadcaster] = None,
        device_service: Optional[DeviceService] = None,
    ):
        self.device_service = device_service or DeviceService()
        self.broadcaster = broadcaster
        self._on_device_discovered: Optional[Callable[[Device], None]] = None
        self._own_broadcaster = False

    @property
    def device_id(self) -> str:
        return self.device_service.get_current_device().id

    @property
    def port(self) -> int:
        return self.device_service.get_current_device().port

    async def start_discovery(
        self, on_device_discovered: Callable[[Device], None]
    ) -> None:
        """Start listening continuously for presence broadcasts on the local network."""
        self._on_device_discovered = on_device_discovered
        self._own_broadcaster = self.broadcaster is None
        if self.broadcaster is None:
            self.broadcaster = Broadcaster(port=self.port)

        self.broadcaster.subscribe(self._handle_packet)
        await self.broadcaster.start()
        logger.info(f"DiscoveryService started continuous listening on port {self.port}.")

    async def stop_discovery(self) -> None:
        """Stop continuous listening for presence broadcasts."""
        if self.broadcaster is not None:
            self.broadcaster.unsubscribe(self._handle_packet)
            if self._own_broadcaster:
                await self.broadcaster.stop()
                self.broadcaster = None
            logger.info("DiscoveryService stopped listening.")

    def _handle_packet(self, packet: Packet, address: tuple[str, int]) -> None:
        if packet.device_id == self.device_id:
            return

        if packet.type in (PacketType.DISCOVER_RESPONSE, PacketType.DISCOVER):
            try:
                device = Device.from_payload(packet.payload, fallback_address=address)
                if self._on_device_discovered:
                    self._on_device_discovered(device)
            except ValueError as err:
                logger.warning(f"Skipping invalid packet payload: {err}")

    async def discover_devices(self, timeout: float = 2.0) -> list[Device]:
        """Scan network packets for `timeout` seconds and return discovered devices."""
        discovered: dict[str, Device] = {}

        def on_device(device: Device) -> None:
            discovered[device.id] = device

        await self.start_discovery(on_device)
        try:
            await asyncio.sleep(timeout)
        finally:
            await self.stop_discovery()

        logger.info(f"Discovered {len(discovered)} device(s).")
        return list(discovered.values())
