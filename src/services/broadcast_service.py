import threading
import time
from typing import Optional

from models.device import Device
from protocol.broadcaster import Broadcaster
from protocol.packet import Packet, PacketType
from protocol.protocol import RLP
from services.device_service import DeviceService
from utils.logger import get_logger

logger = get_logger(__name__)


class BroadcastService:
    """Service responsible for broadcasting presence and custom packets across the LAN network."""

    def __init__(
        self,
        broadcaster: Optional[Broadcaster] = None,
        device_service: Optional[DeviceService] = None,
        interval: float = 2.0,
    ):
        self.device_service = device_service or DeviceService()
        self._broadcaster = broadcaster
        self.interval = interval
        self._stop_event = threading.Event()
        self._loop_thread: Optional[threading.Thread] = None

    @property
    def device(self) -> Device:
        return self.device_service.get_current_device()

    @property
    def port(self) -> int:
        return self.device.port

    def start_private_broadcast(self) -> None:
        """Start transport broadcaster, listen for DISCOVER requests, and continuously send presence broadcasts every `self.interval` seconds."""
        if self._broadcaster is None:
            self._broadcaster = Broadcaster(port=self.port)
        self._broadcaster.subscribe(self._on_packet_received)
        self._broadcaster.start()

        self._stop_event.clear()
        if self._loop_thread is None or not self._loop_thread.is_alive():
            self._loop_thread = threading.Thread(
                target=self._periodic_broadcast_loop,
                daemon=True,
            )
            self._loop_thread.start()

        logger.info(f"BroadcastService started on port {self.port} with {self.interval}s interval.")

    def stop_private_broadcast(self) -> None:
        """Stop continuous broadcasting loop and transport broadcaster."""
        self._stop_event.set()
        if self._loop_thread and self._loop_thread.is_alive():
            self._loop_thread.join(timeout=1.0)
            self._loop_thread = None

        if self._broadcaster is not None:
            self._broadcaster.unsubscribe(self._on_packet_received)
            self._broadcaster.stop()
            self._broadcaster = None
            logger.info("BroadcastService stopped")

    def _periodic_broadcast_loop(self) -> None:
        """Background thread loop broadcasting presence DISCOVER packets every `self.interval` seconds."""
        while not self._stop_event.is_set():
            try:
                self.broadcast()
            except Exception as err:
                logger.error(f"Error in periodic broadcast loop: {err}")
            self._stop_event.wait(self.interval)

    def _on_packet_received(self, packet: Packet, address: tuple[str, int]) -> None:
        """Handle incoming network packets. Responds to DISCOVER packets with DISCOVER_RESPONSE."""
        current_device = self.device
        if packet.device_id == current_device.id:
            return

        if packet.type == PacketType.DISCOVER:
            logger.info(f"Received DISCOVER from {packet.device_id} at {address}. Replying with DISCOVER_RESPONSE.")
            response_packet = Packet(
                type=PacketType.DISCOVER_RESPONSE,
                version=str(RLP.VERSION),
                device_id=current_device.id,
                payload=current_device,
            )
            if self._broadcaster:
                self._broadcaster.send(response_packet, address)

    def broadcast(self, packet: Optional[Packet] = None) -> None:
        """
        Broadcast a packet over the network.
        If no packet is provided, constructs a default DISCOVER presence packet with Device payload.
        """
        if self._broadcaster is None:
            self._broadcaster = Broadcaster(port=self.port)
            self._broadcaster.start()

        current_device = self.device
        if packet is None:
            packet = Packet(
                type=PacketType.DISCOVER,
                version=str(RLP.VERSION),
                device_id=current_device.id,
                payload=current_device,
            )

        logger.info(f"Broadcasting packet type='{packet.type}' over the network")
        self._broadcaster.broadcast(packet)
