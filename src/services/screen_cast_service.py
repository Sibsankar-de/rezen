import base64

from models.connection import Connection
from models.stream_chunk import StreamChunk
from protocol.connection_manager import ConnectionManager
from protocol.packet import Packet, PacketType
from input_control.cursor_tracker import HostCursorTracker
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
        self._cursor_tracker: HostCursorTracker | None = None

        self._sent_chunks = 0
        self._sent_bytes = 0
        self._received_packets = 0

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
        await self._connection_manager.subscribe(self._handle_streamer_packet)
        await self._send_screen_info()
        self._cursor_tracker = HostCursorTracker(self._send_host_cursor)
        await self._cursor_tracker.start()
        await self.streamer.start(self._send_chunk)

    async def _send_host_cursor(self, x: int, y: int, visible: bool) -> None:
        packet = Packet(
            type=PacketType.HOST_CURSOR,
            version="1.0",
            device_id=self._device_service.get_current_device().id,
            payload={"x": x, "y": y, "visible": visible},
        )
        try:
            await self._connection_service.send_to_latest(packet)
        except Exception:
            pass

    async def stop_streaming(self) -> None:
        """Stop and close streaming"""
        logger.info("Stopping screen cast streaming...")
        if self._cursor_tracker is not None:
            await self._cursor_tracker.stop()
            self._cursor_tracker = None
        await self._connection_manager.unsubscribe(self._handle_streamer_packet)
        if self._streamer is not None:
            await self._streamer.stop()
            self._streamer = None

    def _get_host_screen_size(self) -> tuple[int, int]:
        """Determine host screen resolution using streamer or capture backend."""
        if self._streamer is not None:
            size = getattr(self._streamer, "screen_size", None)
            if isinstance(size, (tuple, list)) and len(size) == 2:
                try:
                    return int(size[0]), int(size[1])
                except (TypeError, ValueError):
                    pass
        from screen_cast.capture import get_system_screen_size

        return get_system_screen_size()

    async def _send_screen_info(self) -> None:
        """Create packet and send host screen dimensions to the receiver."""
        w, h = self._get_host_screen_size()
        packet = Packet(
            type=PacketType.SCREEN_INFO,
            version="1.0",
            device_id=self._device_service.get_current_device().id,
            payload={"width": int(w), "height": int(h)},
        )
        logger.info(f"Sending SCREEN_INFO packet: {w}x{h}")
        await self._connection_service.send_to_latest(packet)

    def _verify_connection_packet(
        self,
        connection: Connection,
        packet: Packet | None,
        expected_type: PacketType | None = None,
    ) -> bool:
        """Validate that a packet exists, matches expected type, and belongs to the active connection."""
        if packet is None:
            return False

        if expected_type is not None and packet.type != expected_type:
            return False

        latest = self._connection_service.latest_connection
        if not latest:
            logger.debug(
                f"Received packet {packet.type} but no active latest_connection."
            )
            return False

        conn_dev_id = getattr(connection, "device_id", None)
        latest_dev_id = getattr(latest, "device_id", None)
        if latest.id != connection.id and (
            not conn_dev_id or conn_dev_id != latest_dev_id
        ):
            logger.debug(
                f"Ignoring packet from {connection.id}: does not match active connection {latest.id}."
            )
            return False

        return True

    async def _handle_streamer_packet(
        self, connection: Connection, packet: Packet
    ) -> None:
        if not self._verify_connection_packet(
            connection, packet, PacketType.SCREEN_INFO_REQUEST
        ):
            return
        logger.info(
            f"Received SCREEN_INFO_REQUEST from {connection.id}; sending SCREEN_INFO."
        )
        await self._send_screen_info()

    async def _send_chunk(self, chunk: StreamChunk) -> None:
        """Create packet and send stream chunk"""
        packet = Packet(
            type=PacketType.SCREEN_FRAME_CHUNK,
            version="1.0",
            device_id=self._device_service.get_current_device().id,
            payload=chunk,
        )

        self._sent_chunks += 1
        self._sent_bytes += len(chunk.data or b"")
        if self._sent_chunks == 1:
            logger.info(
                f"Sending first stream chunk: frame={chunk.frame_id} "
                f"chunk={chunk.chunk_id} size={chunk.size} total={chunk.total_chunks}."
            )
        if self._sent_chunks % 100 == 0:
            logger.info(
                f"Sent {self._sent_chunks} stream chunk(s) totalling "
                f"{self._sent_bytes} bytes."
            )

        await self._connection_service.send_to_latest(packet)

    async def start_receiving(self) -> None:
        """Start receiver"""
        logger.info("Starting screen cast receiving...")
        await self.receiver.start()
        await self._connection_manager.subscribe(self._handle_stream_packet)
        await self._connection_manager.subscribe(self._handle_screen_info_packet)
        await self._connection_manager.subscribe(self._handle_host_cursor_packet)
        logger.info(
            f"Screen cast receiving is live; subscribed to stream packets "
            f"({self._connection_manager.get_connection_count()} active connection(s))."
        )
        await self._request_screen_info()

    async def _request_screen_info(self) -> None:
        """Request host screen dimensions from the streamer."""
        packet = Packet(
            type=PacketType.SCREEN_INFO_REQUEST,
            version="1.0",
            device_id=self._device_service.get_current_device().id,
            payload={},
        )
        try:
            await self._connection_service.send_to_latest(packet)
        except Exception as exc:
            logger.debug(f"Could not send SCREEN_INFO_REQUEST: {exc}")

    async def stop_receiving(self) -> None:
        """Stop and clean receiver"""
        logger.info("Stopping screen cast receiving...")
        await self._connection_manager.unsubscribe(self._handle_stream_packet)
        await self._connection_manager.unsubscribe(self._handle_screen_info_packet)
        await self._connection_manager.unsubscribe(self._handle_host_cursor_packet)
        if self._receiver is not None:
            await self._receiver.stop()
            self._receiver = None

    async def _handle_host_cursor_packet(
        self, connection: Connection, packet: Packet
    ) -> None:
        if not self._verify_connection_packet(
            connection, packet, PacketType.HOST_CURSOR
        ):
            return

        payload = packet.payload
        if isinstance(payload, dict):
            x = payload.get("x")
            y = payload.get("y")
            visible = payload.get("visible", True)
            if x is not None and y is not None and self._receiver is not None:
                self.receiver.set_host_cursor(int(x), int(y), bool(visible))

    async def _handle_screen_info_packet(
        self, connection: Connection, packet: Packet
    ) -> None:
        if not self._verify_connection_packet(
            connection, packet, PacketType.SCREEN_INFO
        ):
            return

        payload = packet.payload
        if isinstance(payload, dict):
            w = payload.get("width")
            h = payload.get("height")
            if w and h:
                logger.info(f"Received host SCREEN_INFO: {w}x{h}.")
                self.receiver.set_host_resolution(int(w), int(h))

    async def _handle_stream_packet(
        self, connection: Connection, packet: Packet
    ) -> None:
        if not self._verify_connection_packet(
            connection, packet, PacketType.SCREEN_FRAME_CHUNK
        ):
            return

        if not packet.payload:
            return

        conn_dev_id = getattr(connection, "device_id", None)
        self._received_packets += 1
        if self._received_packets == 1:
            logger.info(
                f"First stream packet received on connection {connection.id} "
                f"from device {conn_dev_id}."
            )
        if self._received_packets % 100 == 0:
            logger.info(f"Received {self._received_packets} stream packet(s).")

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
