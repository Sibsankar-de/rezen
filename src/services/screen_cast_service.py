import base64

from models.connection import Connection
from models.stream_chunk import StreamChunk
from protocol.connection_manager import ConnectionManager
from protocol.packet import Packet, PacketType
from screen_cast.receiver import Receiver
from screen_cast.streamer import Streamer
from services.connection_service import ConnectionService
from services.device_service import DeviceService
from utils.logger import get_logger

logger = get_logger(__name__)


class ScreenCastService:
    """Service to handle screen casting"""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        connection_service: ConnectionService,
        device_service: DeviceService,
        streamer: Streamer | None = None,
        receiver: Receiver | None = None,
    ):
        self._connection_manager = connection_manager
        self._connection_service = connection_service
        self._device_service = device_service

        self._streamer = streamer
        self._receiver = receiver

    @property
    def streamer(self) -> Streamer:
        if self._streamer is None:
            self._streamer = Streamer()
        return self._streamer

    @property
    def receiver(self) -> Receiver:
        if self._receiver is None:
            self._receiver = Receiver()
        return self._receiver

    async def start_streaming(self) -> None:
        """Start streaming"""
        logger.info("Starting screen cast streaming...")
        await self.streamer.start(self._send_chunk)

    async def stop_streaming(self) -> None:
        """Stop and close streaming"""
        logger.info("Stopping screen cast streaming...")
        if self._streamer is not None:
            await self._streamer.stop()
            self._streamer = None

    async def _send_chunk(self, chunk: StreamChunk) -> None:
        """Create packet and send stream chunk"""
        packet = Packet(
            type=PacketType.SCREEN_FRAME_CHUNK,
            version="1.0",
            device_id=self._device_service.get_current_device().id,
            payload=chunk,
        )

        await self._connection_service.send_to_latest(packet)

    async def start_receiving(self) -> None:
        """Start receiver"""
        logger.info("Starting screen cast receiving...")
        await self.receiver.start()
        await self._connection_manager.subscribe(self._handle_stream_packet)

    async def stop_receiving(self) -> None:
        """Stop and clean receiver"""
        logger.info("Stopping screen cast receiving...")
        await self._connection_manager.unsubscribe(self._handle_stream_packet)
        if self._receiver is not None:
            await self._receiver.stop()
            self._receiver = None

    async def _handle_stream_packet(
        self, connection: Connection, packet: Packet
    ) -> None:
        latest = self._connection_service.latest_connection
        if not latest:
            logger.debug("Received stream packet but no active latest_connection.")
            return

        conn_dev_id = getattr(connection, "device_id", None)
        latest_dev_id = getattr(latest, "device_id", None)
        if latest.id != connection.id and (not conn_dev_id or conn_dev_id != latest_dev_id):
            logger.debug(
                f"Ignoring packet from {connection.id}: does not match latest connection {latest.id}"
            )
            return

        if not packet or packet.type != PacketType.SCREEN_FRAME_CHUNK or not packet.payload:
            return

        payload = packet.payload
        if isinstance(payload, dict):
            if isinstance(payload.get("data"), str):
                try:
                    payload["data"] = base64.b64decode(payload["data"])
                except Exception:
                    payload["data"] = payload["data"].encode("utf-8")
            payload = StreamChunk(**payload)
        elif isinstance(payload, StreamChunk) and isinstance(payload.data, str):
            try:
                payload.data = base64.b64decode(payload.data)
            except Exception:
                payload.data = payload.data.encode("utf-8")

        await self.receiver.handle_chunk(payload)
