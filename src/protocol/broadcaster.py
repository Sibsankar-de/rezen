import json
import socket
import threading
from dataclasses import asdict
from typing import Callable
import ipaddress
import psutil

from protocol.packet import Packet
from protocol.protocol import RLP
from protocol.serializer import PacketSerializer
from utils.logger import get_logger

logger = get_logger(__name__)

PacketHandler = Callable[[Packet, tuple[str, int]], None]


class Broadcaster:
    """
    Low-level UDP transport for the Rezen LAN Protocol.

    Responsibilities
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
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
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
        Broadcast a packet to all devices on the LAN across all active network interfaces.
        """
        broadcast_ips = self.get_broadcast_addresses()
        for ip in broadcast_ips:
            try:
                self._send(packet, (ip, self._port))
            except Exception as err:
                logger.debug(f"Failed to send broadcast to {ip}:{self._port}: {err}")
                continue

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

        data = PacketSerializer.dumps(packet)
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

            except Exception as err:
                logger.debug(f"Failed to deserialize packet from {address}: {err}")
                continue

            for handler in tuple(self._handlers):
                try:
                    handler(packet, address)
                except Exception as err:
                    logger.error(f"Error in packet handler: {err}")

    # Serialization
    @staticmethod
    def _deserialize(data: bytes) -> Packet:

        raw = PacketSerializer.loads(data)
        return raw

    @staticmethod
    def get_broadcast_addresses() -> list[str]:
        """
        Return a list of all active IPv4 broadcast addresses across available network interfaces,
        prioritizing physical LAN interfaces, followed by 255.255.255.255, followed by virtual adapters.
        """
        primary_addrs: list[str] = []
        virtual_addrs: list[str] = []

        try:
            interfaces = psutil.net_if_addrs()
            stats = psutil.net_if_stats()

            for interface_name, addresses in interfaces.items():
                stat = stats.get(interface_name)
                if stat and not stat.isup:
                    continue

                is_virtual = any(
                    v in interface_name.lower()
                    for v in ("docker", "br-", "veth", "virbr", "vmnet")
                )

                for address in addresses:
                    if address.family == socket.AF_INET:
                        ip = address.address
                        netmask = address.netmask

                        # Ignore loopback
                        if ip.startswith("127."):
                            continue

                        # If broadcast is explicitly reported by OS
                        if getattr(address, "broadcast", None):
                            target_list = virtual_addrs if is_virtual else primary_addrs
                            target_list.append(address.broadcast)

                        if netmask:
                            try:
                                network = ipaddress.IPv4Network(
                                    f"{ip}/{netmask}",
                                    strict=False,
                                )
                                target_list = virtual_addrs if is_virtual else primary_addrs
                                target_list.append(str(network.broadcast_address))
                            except Exception:
                                pass
        except Exception:
            pass

        primary_addrs.append(RLP.BROADCAST_IP)
        primary_addrs.append("255.255.255.255")

        seen = set()
        result: list[str] = []
        for addr in primary_addrs + virtual_addrs:
            if addr and addr not in seen:
                seen.add(addr)
                result.append(addr)

        return result

    @staticmethod
    def get_broadcast_address() -> str:
        """Return the primary broadcast address or global fallback."""
        addresses = Broadcaster.get_broadcast_addresses()
        return addresses[0] if addresses else "255.255.255.255"

