from dataclasses import dataclass
from typing import Generic, TypeVar
from enum import StrEnum

T = TypeVar("T")


class PacketType(StrEnum):
    DISCOVER = "discover"
    DISCOVER_RESPONSE = "discover_response"
    FILE_REQUEST = "file_request"
    FILE_CHUNK = "file_chunk"
    CLIPBOARD = "clipboard"
    PING = "ping"


@dataclass(slots=True)
class Packet(Generic[T]):
    type: PacketType
    version: str
    device_id: str
    payload: T
