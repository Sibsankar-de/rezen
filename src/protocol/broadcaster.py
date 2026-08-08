import json
import socket
import threading
from dataclasses import asdict
from typing import Callable

from protocol.packet import Packet
from protocol.protocol import RLP
from protocol.serializer import PacketSerializer

PacketHandler = Callable[[Packet, tuple[str, int]], None]


class Broadcaster:
    """
    Low-level UDP transport for the Rezen LAN Protocol.

    Responsibilities
    ----------------
    - Own the UDP socket
    - Send unicast packets
    - Send broadcast packets
    - Receive packets
    - Deserialize packets
    - Dispatch packets to subscribers

    This class is intentionally protocol-agnostic. It does not know
    what packet types mean or how they should be handled.
    """

    def __init__(self, port: int = RLP.DEFAULT_PORT):
        self._port = port

        self._handlers: list[PacketHandler] = []

        self._running = False
        self._thread: threading.Thread | None = None

        self._socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )

        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        self._socket.bind(("", port))

    # Lifecycle
    def start(self) -> None:
        if self._running:
            return

        self._running = True

        self._thread = threading.Thread(
            target=self._listen_loop,
            daemon=True,
            name="Broadcaster",
        )

        self._thread.start()

    def stop(self) -> None:
        self._running = False

        try:
            self._socket.close()
        except OSError:
            pass

        if self._thread is not None:
            self._thread.join(timeout=1)

    # Subscription
    def subscribe(self, handler: PacketHandler) -> None:
        self._handlers.append(handler)

    def unsubscribe(self, handler: PacketHandler) -> None:
        if handler in self._handlers:
            self._handlers.remove(handler)

    # Sending
    def broadcast(self, packet: Packet) -> None:
        """
        Broadcast a packet to all devices on the LAN.
        """

        self._send(
            packet,
            (RLP.BROADCAST_IP, self._port),
        )

    def send(
        self,
        packet: Packet,
        address: tuple[str, int],
    ) -> None:
        """
        Send a packet to a specific device.
        """

        self._send(packet, address)

    def _send(
        self,
        packet: Packet,
        address: tuple[str, int],
    ) -> None:

        data = json.dumps(
            asdict(packet),
            separators=(",", ":"),
        ).encode()

        self._socket.sendto(data, address)

    # Receiving
    def _listen_loop(self) -> None:

        while self._running:

            try:
                data, address = self._socket.recvfrom(RLP.MAX_PACKET_SIZE)

            except OSError:
                break

            try:
                packet = self._deserialize(data)

            except Exception:
                continue

            for handler in tuple(self._handlers):
                handler(packet, address)

    # Serialization
    @staticmethod
    def _deserialize(data: bytes) -> Packet:

        raw = PacketSerializer.loads(data.decode())
        return raw
