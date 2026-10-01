import asyncio

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
        broadcaster_service: BroadcastService,
        device_service: DeviceService,
    ):
        self._connection_manager = connection_manager
        self._broadcaster = broadcaster
        self._broadcaster_service = broadcaster_service
        self._device_service = device_service

        self._latest_connection: Connection | None = None

    @property
    def device(self) -> Device:
        return self._device_service.get_current_device()

    @property
    def latest_connection(self) -> Connection | None:
        return self._latest_connection

    async def request_connection(self, to_device: Device) -> None:
        """Send a connection request to the specified device."""
        logger.info(
            f"Sending connection request to {to_device.name} ({to_device.ip}:{to_device.port})"
        )

        request_packet = Packet(
            type=PacketType.CONNECTION_REQUEST,
            version="1.0",
            device_id=self._device_service.get_current_device().id,
            payload=self.device,
        )

        self._broadcaster.send(request_packet, (to_device.ip, to_device.port))

    async def accept_connection(self, from_device: Device) -> Connection:
        """Accept a connection request from the specified device."""
        logger.info(
            f"Accepting connection from {from_device.name} ({from_device.ip}:{from_device.port})"
        )

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

        try:
            connection = await self._connection_manager.connect(remote_device)
            self._latest_connection = connection
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
        await self._connection_manager.disconnect(connection_id)

    async def get_connection(self, from_device: Device) -> Connection | None:
        """Return the connection state for a requested connection"""
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
        await self._connection_manager.disconnect(connection_id)

    async def send_to_latest(self, packet: Packet) -> None:
        """Send packet to latest connection"""
        if not self._latest_connection:
            return

        await self._connection_manager.send(
            connection_id=self._latest_connection.id, packet=packet
        )
