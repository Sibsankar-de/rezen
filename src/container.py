from __future__ import annotations

from protocol.broadcaster import Broadcaster
from protocol.connection_manager import ConnectionManager
from services.broadcast_service import BroadcastService
from services.connection_service import ConnectionService
from services.device_service import DeviceService
from services.discovery_service import DiscoveryService
from utils.logger import get_logger

logger = get_logger(__name__)


class Container:
    """
    Application-wide dependency container.
    """

    def __init__(self) -> None:
        self._device_service: DeviceService | None = None
        self._broadcaster: Broadcaster | None = None
        self._connection_manager: ConnectionManager | None = None
        self._connection_service: ConnectionService | None = None

    async def start(self) -> None:
        """Start all network-level singletons. Call once at app startup."""
        logger.info("Starting shared network services...")
        await self.broadcaster.start()
        await self.connection_manager.start()
        logger.info("Shared network services started.")

    async def stop(self) -> None:
        """Shut down all network-level singletons. Call once at app teardown."""
        logger.info("Stopping shared network services...")
        if self._connection_manager is not None:
            await self._connection_manager.stop()
        if self._broadcaster is not None:
            await self._broadcaster.stop()
            self._broadcaster = None
        logger.info("Shared network services stopped.")

    @property
    def device_service(self) -> DeviceService:
        """Singleton DeviceService - reads device metadata from the DB."""
        if self._device_service is None:
            self._device_service = DeviceService()
        return self._device_service

    @property
    def broadcaster(self) -> Broadcaster:
        """Singleton Broadcaster - owns the single UDP socket for the app."""
        if self._broadcaster is None:
            device = self.device_service.get_current_device()
            self._broadcaster = Broadcaster(port=device.port)
        return self._broadcaster

    @property
    def connection_manager(self) -> ConnectionManager:
        """Singleton ConnectionManager - owns the TCP server."""
        if self._connection_manager is None:
            device = self.device_service.get_current_device()
            self._connection_manager = ConnectionManager(
                current_device=device,
                port=device.port,
            )
        return self._connection_manager

    @property
    def connection_service(self) -> ConnectionService:
        """Singleton ConnectionService - wraps broadcaster + connection_manager."""
        if self._connection_service is None:
            self._connection_service = ConnectionService(
                broadcaster=self.broadcaster,
                connection_manager=self.connection_manager,
                device_service=self.device_service,
            )
        return self._connection_service

    def broadcast_service(self) -> BroadcastService:
        """
        Create a fresh BroadcastService backed by the shared Broadcaster.
        Each BroadcastScreen gets its own instance so start/stop are isolated.
        """
        return BroadcastService(
            broadcaster=self.broadcaster,
            device_service=self.device_service,
        )

    def discovery_service(self) -> DiscoveryService:
        """
        Create a fresh DiscoveryService backed by the shared Broadcaster.
        Each DiscoverScreen gets its own instance so start/stop are isolated.
        """
        return DiscoveryService(
            broadcaster=self.broadcaster,
            device_service=self.device_service,
        )


container = Container()
