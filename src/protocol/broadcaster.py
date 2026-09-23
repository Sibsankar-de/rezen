import asyncio
import ipaddress
import socket
from typing import Callable

import psutil

from protocol.packet import Packet
from protocol.protocol import RLP
from protocol.serializer import PacketSerializer
from utils.logger import get_logger

logger = get_logger(__name__)

PacketHandler = Callable[[Packet, tuple[str, int]], None]


class _UDPProtocol(asyncio.DatagramProtocol):
    """asyncio DatagramProtocol that dispatches received datagrams to registered handlers."""

    def __init__(self, handlers: list[PacketHandler]) -> None:
        self._handlers = handlers
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            packet = PacketSerializer.loads(data)
        except Exception as err:
            logger.debug(f"Failed to deserialize packet from {addr}: {err}")
            return

        for handler in tuple(self._handlers):
            try:
                handler(packet, addr)
            except Exception as err:
                logger.error(f"Error in packet handler: {err}")

    def error_received(self, exc: Exception) -> None:
        logger.debug(f"UDP error received: {exc}")

    def connection_lost(self, exc: Exception | None) -> None:
        pass


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
        self._transport: asyncio.DatagramTransport | None = None
        self._protocol: _UDPProtocol | None = None

    async def start(self) -> None:
        """Bind the UDP socket and register with the running event loop."""
        if self._transport is not None:
            return

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", self._port))

        self._protocol = _UDPProtocol(self._handlers)
        transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(
            lambda: self._protocol,
            sock=sock,
        )
        self._transport = transport

    async def stop(self) -> None:
        """Close the UDP socket."""
        if self._transport is not None:
            self._transport.close()
            self._transport = None
            self._protocol = None

    def subscribe(self, handler: PacketHandler) -> None:
        self._handlers.append(handler)

    def unsubscribe(self, handler: PacketHandler) -> None:
        if handler in self._handlers:
            self._handlers.remove(handler)

    def broadcast(self, packet: Packet) -> None:
        """Broadcast a packet to all devices on the LAN across all active network interfaces."""
        for ip in self.get_broadcast_addresses():
            try:
                self._send(packet, (ip, self._port))
            except Exception as err:
                logger.debug(f"Failed to send broadcast to {ip}:{self._port}: {err}")

    def send(self, packet: Packet, address: tuple[str, int]) -> None:
        """Send a packet to a specific device."""
        self._send(packet, address)

    def _send(self, packet: Packet, address: tuple[str, int]) -> None:
        data = PacketSerializer.dumps(packet)
        if self._transport is not None and not self._transport.is_closing():
            self._transport.sendto(data, address)
        else:
            logger.warning(f"Broadcaster not started, dropping packet to {address}")

    @staticmethod
    def _deserialize(data: bytes) -> Packet:
        return PacketSerializer.loads(data)

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

                        if ip.startswith("127."):
                            continue

                        if getattr(address, "broadcast", None):
                            target_list = virtual_addrs if is_virtual else primary_addrs
                            target_list.append(address.broadcast)

                        if netmask:
                            try:
                                network = ipaddress.IPv4Network(
                                    f"{ip}/{netmask}",
                                    strict=False,
                                )
                                target_list = (
                                    virtual_addrs if is_virtual else primary_addrs
                                )
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
