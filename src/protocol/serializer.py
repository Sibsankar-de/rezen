import json
import struct
from dataclasses import asdict
from typing import Any

from protocol.packet import Packet, PacketType


class PacketSerializer:
    """
    Serializes and deserializes Rezen LAN Protocol packets.

    The transport layer (Broadcaster) should only work with bytes,
    while the rest of the application works with Packet objects.
    """

    @staticmethod
    def dumps(packet: Packet[Any]) -> bytes:
        """
        Convert a Packet into bytes suitable for network transport.
        """
        return json.dumps(
            asdict(packet),
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    @staticmethod
    def loads(data: bytes) -> Packet[Any]:
        """
        Convert network bytes back into a Packet.
        """
        raw = json.loads(data.decode("utf-8"))

        PacketSerializer._validate(raw)

        pkt_type = raw["type"]
        try:
            pkt_type = PacketType(pkt_type)
        except ValueError:
            pass

        return Packet(
            type=pkt_type,
            version=raw["version"],
            device_id=raw["device_id"],
            payload=raw["payload"],
        )

    @staticmethod
    def _validate(raw: dict[str, Any]) -> None:
        """
        Validate the minimum packet structure.
        """
        required = (
            "type",
            "version",
            "device_id",
            "payload",
        )

        missing = [field for field in required if field not in raw]

        if missing:
            raise ValueError(f"Missing packet field(s): {', '.join(missing)}")


class TCPSerializer:
    """
    Serializes and deserializes Rezen packets for TCP transport.

    TCP is a byte stream, so every serialized packet is prefixed
    with a 4-byte unsigned integer containing the payload length.
    """

    HEADER_SIZE = 4
    MAX_PACKET_SIZE = 64 * 1024

    @classmethod
    async def serialize(cls, packet: Packet[Any]) -> bytes:
        """
        Convert a Packet into a length-prefixed byte frame.
        """

        payload = PacketSerializer.dumps(packet)

        size = len(payload)

        if size > cls.MAX_PACKET_SIZE:
            raise ValueError(f"Packet too large: {size} bytes")

        header = struct.pack("!I", size)

        return header + payload

    @classmethod
    async def deserialize(cls, data: bytes) -> Packet[Any]:
        """
        Deserialize one complete TCP frame.
        """

        if len(data) < cls.HEADER_SIZE:
            raise ValueError("Incomplete TCP frame")

        size = struct.unpack(
            "!I",
            data[: cls.HEADER_SIZE],
        )[0]

        if size > cls.MAX_PACKET_SIZE:
            raise ValueError(f"Packet too large: {size} bytes")

        payload = data[cls.HEADER_SIZE :]

        if len(payload) != size:
            raise ValueError(
                f"Incomplete TCP frame: " f"expected {size}, got {len(payload)}"
            )

        return PacketSerializer.loads(payload)
