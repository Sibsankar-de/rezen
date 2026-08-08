import platform
import socket
import uuid
from typing import Optional

from models.device import Device
from protocol.broadcaster import Broadcaster
from protocol.packet import Packet, PacketType
from protocol.protocol import RLP
from utils.logger import get_logger

logger = get_logger(__name__)


class BroadcastService:
    """Service responsible for broadcasting presence and custom packets across the LAN network."""

    def __init__(
        self,
        config: Optional[dict] = None,
        broadcaster: Optional[Broadcaster] = None,
        device_id: Optional[str] = None,
        port: int = RLP.DEFAULT_PORT,
    ):
        self.config = config or {}
        self.device_id = device_id or self.config.get("device_id") or str(uuid.uuid4())
        self.port = port or self.config.get("port", RLP.DEFAULT_PORT)
        self._broadcaster = broadcaster

    def _get_local_device(self) -> Device:
        return Device(
            id=self.device_id,
            name=self.config.get("name", socket.gethostname()),
            hostname=socket.gethostname(),
            ip=self.config.get("ip", "0.0.0.0"),
            port=self.port,
            os=platform.system(),
        )

    def start_private_broadcast(self) -> None:
        """Start the transport broadcaster and listen for DISCOVER requests to reply with DISCOVER_RESPONSE."""
        if self._broadcaster is None:
            self._broadcaster = Broadcaster(port=self.port)
        self._broadcaster.subscribe(self._on_packet_received)
        self._broadcaster.start()
        logger.info(f"BroadcastService started on port {self.port}")

    def stop_private_broadcast(self) -> None:
        """Stop the transport broadcaster."""
        if self._broadcaster is not None:
            self._broadcaster.unsubscribe(self._on_packet_received)
            self._broadcaster.stop()
            self._broadcaster = None
            logger.info("BroadcastService stopped")

    def _on_packet_received(self, packet: Packet, address: tuple[str, int]) -> None:
        """Handle incoming network packets. Responds to DISCOVER packets with DISCOVER_RESPONSE."""
        if packet.device_id == self.device_id:
            return

        if packet.type == PacketType.DISCOVER:
            logger.info(f"Received DISCOVER from {packet.device_id} at {address}. Replying with DISCOVER_RESPONSE.")
            response_device = self._get_local_device()
            response_packet = Packet(
                type=PacketType.DISCOVER_RESPONSE,
                version=str(RLP.VERSION),
                device_id=self.device_id,
                payload=response_device,
            )
            if self._broadcaster:
                self._broadcaster.send(response_packet, address)

    def broadcast(self, packet: Optional[Packet] = None) -> None:
        """
        Broadcast a packet over the network.
        If no packet is provided, constructs a default DISCOVER presence packet with Device payload.
        """
        if self._broadcaster is None:
            self.start_private_broadcast()

        if packet is None:
            packet = Packet(
                type=PacketType.DISCOVER,
                version=str(RLP.VERSION),
                device_id=self.device_id,
                payload=self._get_local_device(),
            )

        logger.info(f"Broadcasting packet type='{packet.type}' over the network")
        self._broadcaster.broadcast(packet)
