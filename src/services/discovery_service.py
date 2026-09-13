import time
from typing import Optional

from models.device import Device
from protocol.broadcaster import Broadcaster
from protocol.packet import Packet, PacketType
from protocol.protocol import RLP
from services.device_service import DeviceService
from utils.logger import get_logger

logger = get_logger(__name__)


class DiscoveryService:
    """Service to discover Rezen devices on the local network by sending discovery queries and collecting network packets."""

    def __init__(
        self,
        broadcaster: Optional[Broadcaster] = None,
        device_service: Optional[DeviceService] = None,
    ):
        self.device_service = device_service or DeviceService()
        self.broadcaster = broadcaster

    @property
    def device_id(self) -> str:
        return self.device_service.get_current_device().id

    @property
    def port(self) -> int:
        return self.device_service.get_current_device().port

    def collect_packets(
        self, timeout: float = 1.0
    ) -> list[tuple[Packet, tuple[str, int]]]:
        """
        Listen on the network for `timeout` seconds to collect incoming presence/broadcast packets.
        """
        collected: list[tuple[Packet, tuple[str, int]]] = []

        def handle_packet(packet: Packet, address: tuple[str, int]) -> None:
            if packet.device_id != self.device_id:
                collected.append((packet, address))

        own_broadcaster = False
        broadcaster = self.broadcaster

        if broadcaster is None:
            own_broadcaster = True
            broadcaster = Broadcaster(port=self.port)
            broadcaster.start()
        else:
            broadcaster.start()

        try:
            broadcaster.subscribe(handle_packet)
            time.sleep(timeout)
        finally:
            broadcaster.unsubscribe(handle_packet)
            if own_broadcaster:
                broadcaster.stop()

        logger.info(f"Collected {len(collected)} packet(s) from network.")
        return collected

    def discover_devices(self, timeout: float = 1.0) -> list[Device]:
        """Actively scan network packets and return a list of discovered devices."""
        discovered: dict[str, Device] = {}
        collected_packets = self.collect_packets(timeout=timeout)

        for packet, address in collected_packets:
            if packet.type in (PacketType.DISCOVER_RESPONSE, PacketType.DISCOVER):
                try:
                    device = Device.from_payload(packet.payload, fallback_address=address)
                    discovered[device.id] = device
                except ValueError as err:
                    logger.warning(f"Skipping invalid packet payload: {err}")

        logger.info(f"Discovered {len(discovered)} device(s).")
        return list(discovered.values())
