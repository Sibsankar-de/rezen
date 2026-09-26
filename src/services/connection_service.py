from typing import Optional

from models.device import Device
from models.connection import Connection

from protocol.broadcaster import Broadcaster
from protocol.connection_manager import ConnectionManager
from protocol.packet import Packet, PacketType

from services.device_service import DeviceService


class ConnectionService:
    """Service class for managing connections to devices."""

    def __init__(
        self,
        connection_manager: Optional[ConnectionManager] = None,
        broadcaster: Optional[Broadcaster] = None,
        device_service: Optional[DeviceService] = None,
    ):
        self._connection_manager = connection_manager
        self._device_service = device_service or DeviceService()
        self._broadcaster = broadcaster

    @property
    def device(self) -> Device:
        return self._device_service.get_current_device()

    async def _ensure_broadcaster(self) -> None:
        """Start the broadcaster if it is not already running."""
        if self._broadcaster is None:
            self._broadcaster = Broadcaster(port=self.device.port)
            await self._broadcaster.start()

    async def _ensure_connection_manager(self) -> None:
        """Start the connection manager if it is not already running."""
        if self._connection_manager is None:
            self._connection_manager = ConnectionManager(
                current_device=self.device, port=self.device.port
            )
            await self._connection_manager.start()

    async def request_connection(self, to_device: Device) -> None:
        """Send a connection request to the specified device."""
        await self._ensure_broadcaster()

        request_packet = Packet(
            type=PacketType.CONNECTION_REQUEST,
            version="1.0",
            device_id=self._device_service.get_current_device().id,
            payload=self.device,
        )

        await self._broadcaster.send(request_packet, (to_device.ip, to_device.port))

        # start the connection manager
        await self._ensure_connection_manager()

    async def accept_connection(self, from_device: Device) -> Connection:
        """Accept a connection request from the specified device."""
        await self._ensure_broadcaster()

        accept_packet = Packet(
            type=PacketType.CONNECTION_ACCEPTED,
            version="1.0",
            device_id=self._device_service.get_current_device().id,
            payload=self.device,
        )

        await self._broadcaster.send(accept_packet, (from_device.ip, from_device.port))

        return await self._establish_connection(from_device)

    async def _establish_connection(self, remote_device: Device) -> Connection:
        """Creates a new long lived connection"""
        await self._ensure_connection_manager()

        return await self._connection_manager.connect(remote_device)

    async def disconnect_connection(self, connection_id: str) -> None:
        """Disconnect a connection"""
        self._ensure_connection_manager()
        self._connection_manager.disconnect(connection_id)
