import asyncio
from typing import Optional, Callable

from models.device import Device
from protocol.broadcaster import Broadcaster
from protocol.packet import Packet, PacketType
from protocol.protocol import RLP
from services.device_service import DeviceService
from utils.logger import get_logger

logger = get_logger(__name__)


class BroadcastService:
    """Service responsible for broadcasting presence packets across the LAN network."""

    def __init__(
        self,
        broadcaster: Broadcaster,
        device_service: DeviceService,
        interval: float = 2.0,
    ):
        self._broadcaster = broadcaster
        self.device_service = device_service
        self.interval = interval
        self._broadcast_task: asyncio.Task | None = None

        self._on_connection_request: Optional[Callable[[Device], None]] = None

    @property
    def _device(self) -> Device:
        return self.device_service.get_current_device()

    @property
    def port(self) -> int:
        return self._device.port

    async def start_private_broadcast(
        self, on_connection_request: Optional[Callable[[Device], None]] = None
    ) -> None:
        """Start continuous presence packet broadcasting every `self.interval` seconds."""
        if on_connection_request is not None:
            self._on_connection_request = on_connection_request

        self._broadcaster.subscribe(self._handle_request_packets)

        if self._broadcast_task is not None and not self._broadcast_task.done():
            logger.info(
                f"BroadcastService already broadcasting on port {self.port}; "
                "reusing the running loop."
            )
            return

        self._broadcast_task = asyncio.create_task(self._periodic_broadcast_loop())

        logger.info(
            f"BroadcastService started on port {self.port} with {self.interval}s interval."
        )

    async def stop_private_broadcast(self) -> None:
        """Stop continuous broadcasting loop and unsubscribe."""
        task = self._broadcast_task
        self._broadcast_task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._broadcaster.unsubscribe(self._handle_request_packets)
        logger.info("BroadcastService stopped")

    async def _periodic_broadcast_loop(self) -> None:
        """Broadcast presence DISCOVER packets every `self.interval` seconds."""
        while True:
            try:
                await self.broadcast()
            except Exception as err:
                logger.error(f"Error in periodic broadcast loop: {err}")
            try:
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break

    async def broadcast(self, packet: Optional[Packet] = None) -> None:
        """
        Broadcast a packet over the network.
        If no packet is provided, constructs a default DISCOVER presence packet with Device payload.
        """
        current_device = self._device
        if packet is None:
            packet = Packet(
                type=PacketType.DISCOVER,
                version=str(RLP.VERSION),
                device_id=current_device.id,
                payload=current_device,
            )

        logger.info(f"Broadcasting packet type='{packet.type}' over the network")
        self._broadcaster.broadcast(packet)

    def _handle_request_packets(self, packet: Packet, address: tuple[str, int]) -> None:
        """Handles incoming connection request packet from a device."""
        if packet.device_id == self._device.id:
            return

        if packet.type == PacketType.CONNECTION_REQUEST:
            try:
                device = Device.from_payload(packet.payload, fallback_address=address)
                if self._on_connection_request:
                    self._on_connection_request(device)
            except ValueError as err:
                logger.warning(f"Skipping invalid packet payload: {err}")
