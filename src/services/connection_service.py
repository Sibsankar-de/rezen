from typing import Optional

from models.device import Device
from models.connection import Connection

from protocol.broadcaster import Broadcaster
from protocol.packet import Packet, PacketType

from services.device_service import DeviceService


class ConnectionService:
    """Service class for managing connections to devices."""

    def __init__(
        self,
        broadcaster: Optional[Broadcaster] = None,
        device_service: Optional[DeviceService] = None,
    ):
        self.device_service = device_service or DeviceService()
        self.broadcaster = broadcaster

        self.active_connection: Connection | None = None

    @property
    def device(self) -> Device:
        return self.device_service.get_current_device()

    async def _start_broadcaster(self) -> None:
        """Start the broadcaster if it is not already running."""
        if self.broadcaster is None:
            self.broadcaster = Broadcaster(port=self.device.port)
            await self.broadcaster.start()

    async def request_connection(self, to_device: Device) -> None:
        """Send a connection request to the specified device."""
        await self._start_broadcaster()

        request_packet = Packet(
            type=PacketType.CONNECTION_REQUEST,
            version="1.0",
            device_id=self.device_service.get_current_device().id,
            payload=self.device,
        )

        self.broadcaster.send(request_packet, (to_device.ip, to_device.port))

    async def accept_connection(self, from_device: Device) -> None:
        """Accept a connection request from the specified device."""
        await self._start_broadcaster()

        accept_packet = Packet(
            type=PacketType.CONNECTION_ACCEPTED,
            version="1.0",
            device_id=self.device_service.get_current_device().id,
            payload=self.device,
        )

        self.broadcaster.send(accept_packet, (from_device.ip, from_device.port))

    def _start_connection(self):
        """Creates a new long lived connection"""
