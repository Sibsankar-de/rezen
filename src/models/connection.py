from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Optional
import asyncio


class ConnectionState(StrEnum):
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"


@dataclass
class Connection:
    id: str
    device_id: str

    remote_ip: str
    remote_port: int

    state: ConnectionState

    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter

    connected_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None

    reconnect_attempts: int = 0

    receive_task: Optional[asyncio.Task] = None
