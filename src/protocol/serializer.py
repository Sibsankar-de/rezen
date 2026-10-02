import asyncio
import base64
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
        def _default(obj: Any) -> Any:
            if isinstance(obj, (bytes, bytearray)):
                return {"__bytes__": base64.b64encode(obj).decode("ascii")}
            raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

        return json.dumps(
            asdict(packet),
            default=_default,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    @staticmethod
    def loads(data: bytes) -> Packet[Any]:
        """
        Convert network bytes back into a Packet.
        """
        def _object_hook(obj: dict[str, Any]) -> Any:
            if "__bytes__" in obj and len(obj) == 1:
                return base64.b64decode(obj["__bytes__"])
            return obj

        raw = json.loads(data.decode("utf-8"), object_hook=_object_hook)

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
    MAX_PACKET_SIZE = 1024 * 1024  # 1 MB

    @classmethod
    def serialize(cls, packet: Packet[Any]) -> bytes:
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
    async def deserialize(
        cls, stream_or_data: asyncio.StreamReader | bytes
    ) -> Packet[Any]:
        """
        Deserialize one complete TCP frame from an asyncio.StreamReader or bytes.
        """
        if isinstance(stream_or_data, asyncio.StreamReader):
            header = await stream_or_data.readexactly(cls.HEADER_SIZE)
            (size,) = struct.unpack("!I", header)

            if size > cls.MAX_PACKET_SIZE:
                raise ValueError(f"Packet too large: {size} bytes")

            payload = await stream_or_data.readexactly(size)
            return PacketSerializer.loads(payload)

        data = stream_or_data
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
                f"Incomplete TCP frame: expected {size}, got {len(payload)}"
            )

        return PacketSerializer.loads(payload)
