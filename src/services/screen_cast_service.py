import asyncio
from typing import Optional

from models.stream_chunk import StreamChunk
from models.connection import Connection

from protocol.packet import Packet, PacketType
from protocol.connection_manager import ConnectionManager

from screen_cast.streamer import Streamer
from screen_cast.receiver import Receiver

from services.connection_service import ConnectionService
from services.device_service import DeviceService


class ScreenCastService:
    """Service to handle screen casting"""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        connection_service: ConnectionService,
        device_service: DeviceService,
        streamer: Optional[Streamer],
        receiver: Optional[Receiver],
    ):
        self._connection_manager = connection_manager
        self._connection_service = connection_service
        self._device_service = device_service

        self._streamer = streamer or Streamer()
        self._receiver = receiver or Receiver()

    async def start_streaming(self) -> None:
        """Start streaming"""
        await self._streamer.start(self._send_chunk)

    async def stop_streaming(self) -> None:
        """Stop and close streaming"""
        await self._streamer.stop()

    async def _send_chunk(self, chunk: StreamChunk) -> None:
        """Create packet and send stream chunk"""
        packet = Packet(
            type=PacketType.SCREEN_FRAME_CHUNK,
            device_id=self._device_service.get_current_device().id,
            payload=chunk,
        )

        await self._connection_service.send_to_latest(packet)

    async def start_receiving(self) -> None:
        """Start receiver"""
        await self._receiver.start()
        await self._connection_manager.subscribe(self._handle_stream_packet)

    async def stop_receiving(self) -> None:
        """Stop and clean receiver"""
        await self._connection_manager.unsubscribe(self._handle_stream_packet)
        await self._receiver.stop()

    async def _handle_stream_packet(
        self, connection: Connection, packet: Packet
    ) -> None:
        """Handle incoming stream packets"""
        if (
            not self._connection_service.latest_connection
            or self._connection_service.latest_connection.id != connection.id
        ):
            return

        if not packet or not packet.payload:
            return

        await self._receiver.handle_chunk(packet.payload)
