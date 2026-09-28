import asyncio
from typing import Optional

from models.device import Device
from models.connection import Connection, ConnectionState

from protocol.broadcaster import Broadcaster
from protocol.connection_manager import ConnectionManager
from protocol.packet import Packet, PacketType

from services.device_service import DeviceService
from services.broadcast_service import BroadcastService
from utils.logger import get_logger

logger = get_logger(__name__)


class ConnectionService:
    """Service class for managing connections to devices."""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        broadcaster: Broadcaster,
        broadcaster_service: Optional[BroadcastService] = None,
        device_service: Optional[DeviceService] = None,
    ):
        self._connection_manager = connection_manager
        self._device_service = device_service or DeviceService()
        self._broadcaster = broadcaster
        self._broadcaster_service = broadcaster_service or BroadcastService(
            broadcaster=self._broadcaster,
            device_service=self._device_service,
        )

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
        logger.info(
            f"Sending connection request to {to_device.name} ({to_device.ip}:{to_device.port})"
        )
        await self._ensure_broadcaster()

        request_packet = Packet(
            type=PacketType.CONNECTION_REQUEST,
            version="1.0",
            device_id=self._device_service.get_current_device().id,
            payload=self.device,
        )

        self._broadcaster.send(request_packet, (to_device.ip, to_device.port))

        # start the connection manager
        await self._ensure_connection_manager()

    async def accept_connection(self, from_device: Device) -> Connection:
        """Accept a connection request from the specified device."""
        logger.info(
            f"Accepting connection from {from_device.name} ({from_device.ip}:{from_device.port})"
        )
        await self._ensure_broadcaster()

        accept_packet = Packet(
            type=PacketType.CONNECTION_ACCEPTED,
            version="1.0",
            device_id=self._device_service.get_current_device().id,
            payload=self.device,
        )

        self._broadcaster.send(accept_packet, (from_device.ip, from_device.port))

        return await self._establish_connection(from_device)

    async def _establish_connection(self, remote_device: Device) -> Connection:
        """Creates a new long lived connection"""
        logger.info(
            f"Establishing TCP connection with {remote_device.name} ({remote_device.ip})"
        )
        await self._ensure_connection_manager()

        try:
            connection = await self._connection_manager.connect(remote_device)
            logger.info(
                f"Connection established: id={connection.id} with {remote_device.name}"
            )
            return connection
        except Exception:
            logger.error(
                f"Failed to establish connection with {remote_device.name}",
                exc_info=True,
            )
            raise

    async def disconnect_connection(self, connection_id: str) -> None:
        """Disconnect a connection"""
        logger.info(f"Disconnecting connection id={connection_id}")
        await self._ensure_connection_manager()
        await self._connection_manager.disconnect(connection_id)

    async def get_connection(self, from_device: Device) -> Connection | None:
        """Return the connection state for a requested connection"""
        await self._ensure_connection_manager()

        connection_id = self._connection_manager.get_connection_id(from_device)
        connection = self._connection_manager.get_connection(connection_id)

        return connection

    async def complete_connection(self, connection: Connection | None) -> bool:
        """Completes connection between two devices and stops broadcaster"""

        if not connection:
            return False

        # stops the broadcasting
        try:
            await self._broadcaster_service.stop_private_broadcast()
        except Exception:
            logger.warning(f"Failed to stop private broadcasting")

        return True

    async def wait_for_connection(
        self,
        from_device: Device,
        timeout: float = 30.0,
        interval: float = 0.5,
    ) -> Connection | None:
        """Poll get_connection in a loop until connection is established, then complete it."""
        loop = asyncio.get_running_loop()
        start_time = loop.time()
        while (loop.time() - start_time) < timeout:
            connection = await self.get_connection(from_device)
            if connection is not None and connection.state == ConnectionState.CONNECTED:
                await self.complete_connection(connection)
                return connection
            await asyncio.sleep(interval)

        return None

    async def close_connection(self, connection_id: str) -> None:
        """Close or disconnect a connection"""
        logger.info(f"Closing connection id={connection_id}")
        await self._ensure_connection_manager()
        await self._connection_manager.disconnect(connection_id)
