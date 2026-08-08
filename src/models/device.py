from dataclasses import dataclass
from typing import Any


@dataclass
class Device:
    id: str
    name: str
    hostname: str
    ip: str
    port: int
    os: str

    @classmethod
    def from_dict(cls, data: dict[str, Any], fallback_address: tuple[str, int] | None = None) -> "Device":
        """Construct a Device instance from a dictionary representation."""
        ip = data.get("ip")
        if not ip or ip == "0.0.0.0":
            ip = fallback_address[0] if fallback_address else "127.0.0.1"

        port = data.get("port")
        if port is None and fallback_address:
            port = fallback_address[1]

        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", ip)),
            hostname=str(data.get("hostname", ip)),
            ip=str(ip),
            port=int(port) if port is not None else 45871,
            os=str(data.get("os", "Unknown")),
        )

    @classmethod
    def from_payload(cls, payload: Any, fallback_address: tuple[str, int] | None = None) -> "Device":
        """Convert a packet payload (Device instance or dict) into a Device object."""
        if isinstance(payload, cls):
            if (not payload.ip or payload.ip == "0.0.0.0") and fallback_address:
                return cls(
                    id=payload.id,
                    name=payload.name,
                    hostname=payload.hostname,
                    ip=fallback_address[0],
                    port=payload.port,
                    os=payload.os,
                )
            return payload
        if isinstance(payload, dict):
            return cls.from_dict(payload, fallback_address=fallback_address)
        raise ValueError(f"Cannot convert payload of type {type(payload)} to Device")
