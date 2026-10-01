from dataclasses import dataclass
from typing import Generic, TypeVar
from enum import StrEnum

T = TypeVar("T")


class PacketType(StrEnum):
    DISCOVER = "discover"
    DISCOVER_RESPONSE = "discover_response"
    CONNECTION_REQUEST = "connection_request"
    CONNECTION_ACCEPTED = "connection_accepted"
    HELLO = "hello"
    HELLO_ACK = "hello_ack"
    CLIPBOARD = "clipboard"
    PING = "ping"

    SCREEN_FRAME_CHUNK = "screen_frame_chunk"


@dataclass(slots=True)
class Packet(Generic[T]):
    type: PacketType
    version: str
    device_id: str
    payload: T
