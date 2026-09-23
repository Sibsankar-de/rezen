import asyncio
from typing import Optional

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
        broadcaster: Optional[Broadcaster] = None,
        device_service: Optional[DeviceService] = None,
        interval: float = 2.0,
    ):
        self.device_service = device_service or DeviceService()
        self._broadcaster = broadcaster
        self.interval = interval
        self._broadcast_task: asyncio.Task | None = None

    @property
    def device(self) -> Device:
        return self.device_service.get_current_device()

    @property
    def port(self) -> int:
        return self.device.port

    async def start_private_broadcast(self) -> None:
        """Start the UDP broadcaster and continuously send presence packets every `self.interval` seconds."""
        if self._broadcaster is None:
            self._broadcaster = Broadcaster(port=self.port)
        await self._broadcaster.start()
        self._broadcast_task = asyncio.create_task(self._periodic_broadcast_loop())
        logger.info(f"BroadcastService started on port {self.port} with {self.interval}s interval.")

    async def stop_private_broadcast(self) -> None:
        """Stop continuous broadcasting loop and close the UDP broadcaster."""
        if self._broadcast_task is not None:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
            self._broadcast_task = None

        if self._broadcaster is not None:
            await self._broadcaster.stop()
            self._broadcaster = None
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
        if self._broadcaster is None:
            self._broadcaster = Broadcaster(port=self.port)
            await self._broadcaster.start()

        current_device = self.device
        if packet is None:
            packet = Packet(
                type=PacketType.DISCOVER,
                version=str(RLP.VERSION),
                device_id=current_device.id,
                payload=current_device,
            )

        logger.info(f"Broadcasting packet type='{packet.type}' over the network")
        self._broadcaster.broadcast(packet)
