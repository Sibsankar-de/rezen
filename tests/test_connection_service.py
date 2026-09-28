import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from models.device import Device
from models.connection import Connection, ConnectionState
from services.connection_service import ConnectionService


@pytest.fixture
def mock_device():
    return Device(
        id="dev1",
        name="Device One",
        hostname="h1",
        ip="127.0.0.1",
        port=45871,
        os="Linux",
    )


@pytest.fixture
def connection_service(mock_device):
    cm = MagicMock()
    bc = MagicMock()
    bcs = MagicMock()
    bcs.stop_private_broadcast = AsyncMock()
    ds = MagicMock()
    ds.get_current_device.return_value = mock_device

    service = ConnectionService(
        connection_manager=cm,
        broadcaster=bc,
        broadcaster_service=bcs,
        device_service=ds,
    )
    return service, cm, bcs


@pytest.mark.asyncio
async def test_get_connection_returns_none_when_not_found(connection_service, mock_device):
    service, cm, _ = connection_service
    cm.get_connection_id.return_value = "dev1:127.0.0.1:45871"
    cm.get_connection.return_value = None
    cm._connections = {}

    result = await service.get_connection(mock_device)
    assert result is None


@pytest.mark.asyncio
async def test_get_connection_returns_connection_when_found(connection_service, mock_device):
    service, cm, _ = connection_service
    cm.get_connection_id.return_value = "dev1:127.0.0.1:45871"

    conn = MagicMock(spec=Connection)
    conn.id = "dev1:127.0.0.1:45871"
    conn.device_id = "dev1"
    conn.state = ConnectionState.CONNECTED
    cm.get_connection.return_value = conn

    result = await service.get_connection(mock_device)
    assert result == conn


@pytest.mark.asyncio
async def test_complete_connection_none_returns_false(connection_service):
    service, _, bcs = connection_service
    result = await service.complete_connection(None)
    assert result is False
    bcs.stop_private_broadcast.assert_not_called()


@pytest.mark.asyncio
async def test_complete_connection_stops_broadcast(connection_service):
    service, _, bcs = connection_service
    conn = MagicMock(spec=Connection)
    result = await service.complete_connection(conn)
    assert result is True
    bcs.stop_private_broadcast.assert_awaited_once()


@pytest.mark.asyncio
async def test_wait_for_connection_success(connection_service, mock_device):
    service, cm, bcs = connection_service
    cm.get_connection_id.return_value = "dev1:127.0.0.1:45871"

    conn = MagicMock(spec=Connection)
    conn.id = "dev1:127.0.0.1:45871"
    conn.device_id = "dev1"
    conn.state = ConnectionState.CONNECTED
    cm.get_connection.return_value = conn

    result = await service.wait_for_connection(mock_device, timeout=1.0, interval=0.05)
    assert result == conn
    bcs.stop_private_broadcast.assert_awaited_once()


@pytest.mark.asyncio
async def test_wait_for_connection_timeout(connection_service, mock_device):
    service, cm, bcs = connection_service
    cm.get_connection_id.return_value = "dev1:127.0.0.1:45871"
    cm.get_connection.return_value = None
    cm._connections = {}

    result = await service.wait_for_connection(mock_device, timeout=0.1, interval=0.02)
    assert result is None
    bcs.stop_private_broadcast.assert_not_called()


@pytest.mark.asyncio
async def test_close_connection_calls_disconnect(connection_service):
    service, cm, _ = connection_service
    cm.disconnect = AsyncMock()

    await service.close_connection("conn_123")
    cm.disconnect.assert_awaited_once_with("conn_123")

