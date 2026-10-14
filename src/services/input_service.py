from models.input import InputObject

from models.connection import Connection
from protocol.packet import Packet, PacketType
from protocol.connection_manager import ConnectionManager
from input_control.streamer import InputStreamer
from input_control.receiver import InputReceiver
from services.connection_service import ConnectionService
from services.device_service import DeviceService
from utils.logger import get_logger

logger = get_logger(__name__)


class InputService:
    """Service to manage input events"""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        connection_service: ConnectionService,
        device_service: DeviceService,
        input_streamer: InputStreamer | None = None,
        input_receiver: InputReceiver | None = None,
    ):
        self._connection_manager = connection_manager
        self._connection_service = connection_service
        self._device_service = device_service

        self._input_streamer = input_streamer
        self._input_receiver = input_receiver

    @property
    def input_streamer(self) -> InputStreamer:
        if self._input_streamer is None:
            self._input_streamer = InputStreamer()
        return self._input_streamer

    @property
    def input_receiver(self) -> InputReceiver:
        if self._input_receiver is None:
            self._input_receiver = InputReceiver()
        return self._input_receiver

    async def start_streamer(self) -> None:
        """Start the input streamer"""
        logger.info("Starting input streaming...")
        await self._input_streamer.start(self._handle_send_event)

    async def stop_streamer(self) -> None:
        """Stop the input streamer"""
        logger.info("Stopping input streaming...")
        if self._input_streamer is not None:
            await self._input_streamer.start()
            self._input_streamer = None

    async def _handle_send_event(self, event: InputObject) -> None:
        """Handle sending the packet to a connection"""
        packet = Packet(
            type=PacketType.INPUT_EVENT,
            device_id=self._device_service.get_current_device().id,
            payload=event,
        )

        await self._connection_service.send_to_latest(packet)

    async def start_receiver(self) -> None:
        """Start the input receiver"""
        logger.info("Starting input receiver...")
        await self._input_receiver.start()
        await self._connection_manager.subscribe(self._handle_input_packet)

    async def stop_receiver(self) -> None:
        """Stop the input receiver"""
        logger.info("Stopping input receiver...")
        await self._input_receiver.stop()
        await self._connection_manager.unsubscribe(self._handle_input_packet)

    async def _handle_input_packet(
        self, connection: Connection, packet: Packet
    ) -> None:
        """Handle incoming input packets"""
        latest = self._connection_service.latest_connection
        if not latest:
            logger.debug("Received input packet but no active latest_connection.")
            return

        conn_dev_id = getattr(connection, "device_id", None)
        latest_dev_id = getattr(latest, "device_id", None)
        if latest.id != connection.id and (
            not conn_dev_id or conn_dev_id != latest_dev_id
        ):
            logger.debug(
                f"Ignoring packet from {connection.id}: does not match latest connection {latest.id}"
            )
            return

        if not packet or packet.type != PacketType.INPUT_EVENT or not packet.payload:
            return

        payload = packet.payload
        if not isinstance(payload, InputObject):
            return

        await self._input_receiver.receive_input(payload)
