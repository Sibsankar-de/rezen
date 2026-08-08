import json
from dataclasses import asdict
from typing import Any

from protocol.packet import Packet


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

        return Packet(
            type=raw["type"],
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
