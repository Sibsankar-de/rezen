from models.input import InputObject, InputType

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
        await self.input_streamer.start(self._handle_send_event)

    async def stop_streamer(self) -> None:
        """Stop the input streamer"""
        logger.info("Stopping input streaming...")
        if self._input_streamer is not None:
            await self._input_streamer.stop()
            self._input_streamer = None

    async def _handle_send_event(self, event: InputObject) -> None:
        """Handle sending the packet to a connection"""
        latest = self._connection_service.latest_connection
        if not latest:
            logger.warning(
                f"[SERVICE] Cannot send INPUT_EVENT packet: no active latest_connection. "
                f"Dropped event: {event.data}"
            )
            return

        current_dev = self._device_service.get_current_device()
        packet = Packet(
            type=PacketType.INPUT_EVENT,
            version="1.0",
            device_id=current_dev.id,
            payload=event,
        )

        logger.info(
            f"[SERVICE] Sending INPUT_EVENT packet to connection {latest.id} "
            f"(remote device: {latest.device_id}) | data: {event.data}"
        )
        await self._connection_service.send_to_latest(packet)

    async def start_receiver(self) -> None:
        """Start the input receiver"""
        logger.info("Starting input receiver...")
        await self.input_receiver.start()
        await self._connection_manager.subscribe(self._handle_input_packet)
        logger.info("Input receiver subscribed to incoming packets.")

    async def stop_receiver(self) -> None:
        """Stop the input receiver"""
        logger.info("Stopping input receiver...")
        await self._connection_manager.unsubscribe(self._handle_input_packet)
        if self._input_receiver is not None:
            await self._input_receiver.stop()
            self._input_receiver = None
        logger.info("Input receiver stopped cleanly.")

    async def _handle_input_packet(
        self, connection: Connection, packet: Packet
    ) -> None:
        """Handle incoming input packets"""
        if not packet or packet.type != PacketType.INPUT_EVENT:
            return

        conn_dev_id = getattr(connection, "device_id", None)
        logger.info(
            f"[SERVICE] Incoming INPUT_EVENT packet on connection {connection.id} "
            f"(device: {conn_dev_id})"
        )

        latest = self._connection_service.latest_connection
        if not latest:
            logger.warning(
                f"[SERVICE] Received INPUT_EVENT on {connection.id} but no active latest_connection. "
                f"Dropping packet."
            )
            return

        latest_dev_id = getattr(latest, "device_id", None)
        if latest.id != connection.id and (
            not conn_dev_id or conn_dev_id != latest_dev_id
        ):
            logger.warning(
                f"[SERVICE] Ignoring packet from connection {connection.id} (device {conn_dev_id}): "
                f"does not match active latest connection {latest.id} (device {latest_dev_id})"
            )
            return

        if not packet.payload:
            logger.warning(
                f"[SERVICE] Received INPUT_EVENT packet with empty payload from {connection.id}"
            )
            return

        payload = packet.payload
        if isinstance(payload, dict):
            payload = InputObject(
                type=InputType(payload.get("type", InputType.KEYBOARD)),
                data=set(payload.get("data", [])),
            )
        elif isinstance(payload, InputObject):
            if not isinstance(payload.data, set):
                payload.data = set(payload.data)
        else:
            logger.warning(
                f"[SERVICE] Received INPUT_EVENT with unsupported payload type: {type(payload)}"
            )
            return

        logger.info(
            f"[SERVICE] Forwarding INPUT_EVENT to receiver: type={payload.type}, data={payload.data}"
        )
        await self.input_receiver.receive_input(payload)
