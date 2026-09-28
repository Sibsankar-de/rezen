import pytest
from textual.widgets import Button
from ui.app import RezenApp
from ui.layout import BaseLayout
from ui.screens.broadcast import BroadcastScreen
from ui.screens.discover import DiscoverScreen
from ui.screens.home import HomeScreen


@pytest.mark.asyncio
async def test_rezen_app_mounts_home_screen():
    app = RezenApp()
    async with app.run_test() as pilot:
        assert isinstance(pilot.app.screen, HomeScreen)
        assert pilot.app.screen.query_one(BaseLayout) is not None
        assert pilot.app.screen.query_one("#welcome-card") is not None
        assert pilot.app.screen.query_one("#btn-broadcast") is not None
        assert pilot.app.screen.query_one("#btn-discover") is not None


@pytest.mark.asyncio
async def test_rezen_app_navigate_to_broadcast_screen():
    app = RezenApp()
    async with app.run_test() as pilot:
        await pilot.click("#btn-broadcast")
        await pilot.pause()
        assert isinstance(pilot.app.screen, BroadcastScreen)
        assert pilot.app.screen.query_one("#broadcast-card") is not None

        pilot.app.screen.query_one("#btn-back", Button).press()
        await pilot.pause()
        assert isinstance(pilot.app.screen, HomeScreen)


@pytest.mark.asyncio
async def test_rezen_app_navigate_to_discover_screen():
    app = RezenApp()
    async with app.run_test() as pilot:
        await pilot.click("#btn-discover")
        await pilot.pause()
        assert isinstance(pilot.app.screen, DiscoverScreen)
        assert pilot.app.screen.query_one("#discover-card") is not None
        assert pilot.app.screen._scan_timer is not None

        await pilot.click("#btn-back")
        await pilot.pause()
        assert isinstance(pilot.app.screen, HomeScreen)


@pytest.mark.asyncio
async def test_connecting_screen_shows_connected_successfully():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from textual.app import App
    from models.device import Device
    from models.connection import Connection, ConnectionState
    from ui.screens.connecting import ConnectingScreen

    class MockApp(App):
        def __init__(self, screen):
            super().__init__()
            self._screen = screen

        def on_mount(self):
            self.push_screen(self._screen)

    dev = Device(id="remote_dev", name="Remote Box", hostname="rbox", ip="127.0.0.1", port=45871, os="Linux")
    cs = MagicMock()
    cs.request_connection = AsyncMock()
    conn = MagicMock(spec=Connection)
    conn.id = "remote_dev:127.0.0.1:45871"
    conn.state = ConnectionState.CONNECTED
    cs.get_connection = AsyncMock(return_value=conn)
    cs.complete_connection = AsyncMock(return_value=True)

    screen = ConnectingScreen(device=dev, connection_service=cs)
    app = MockApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        await asyncio.sleep(0.6)
        await pilot.pause()
        # Verify active screen is now ConnectedScreen
        from ui.screens.connected import ConnectedScreen
        assert isinstance(pilot.app.screen, ConnectedScreen)
        assert "Connected to Remote Box" in str(pilot.app.screen.query_one("#connected-subtitle").content)

        # Check Disconnect button
        btn = pilot.app.screen.query_one("#btn-disconnect", Button)
        assert str(btn.label) == "Disconnect"
        cs.close_connection = AsyncMock()
        btn.press()
        await pilot.pause()
        cs.close_connection.assert_awaited_once_with("remote_dev:127.0.0.1:45871")



@pytest.mark.asyncio
async def test_connected_screen_disconnect_calls_close_connection():
    from unittest.mock import AsyncMock, MagicMock
    from textual.app import App
    from models.device import Device
    from models.connection import Connection, ConnectionState
    from ui.screens.connected import ConnectedScreen

    class MockApp(App):
        def __init__(self, screen):
            super().__init__()
            self._screen = screen

        def on_mount(self):
            self.push_screen(self._screen)

    dev = Device(id="peer_dev", name="Peer Box", hostname="pbox", ip="127.0.0.1", port=45871, os="Linux")
    conn = MagicMock(spec=Connection)
    conn.id = "peer_dev:127.0.0.1:45871"
    conn.state = ConnectionState.CONNECTED

    cs = MagicMock()
    cs.close_connection = AsyncMock()

    screen = ConnectedScreen(device=dev, connection=conn, connection_service=cs)
    app = MockApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        btn = screen.query_one("#btn-disconnect", Button)
        assert str(btn.label) == "Disconnect"
        btn.press()
        await pilot.pause()
        cs.close_connection.assert_awaited_once_with("peer_dev:127.0.0.1:45871")


@pytest.mark.asyncio
async def test_broadcast_screen_transitions_to_connected_screen():
    from unittest.mock import AsyncMock, MagicMock
    from textual.app import App
    from models.device import Device
    from models.connection import Connection, ConnectionState
    from ui.screens.broadcast import BroadcastScreen
    from ui.screens.connected import ConnectedScreen

    dev = Device(id="client_dev", name="Client Device", hostname="cbox", ip="127.0.0.1", port=45871, os="Linux")
    conn = MagicMock(spec=Connection)
    conn.id = "client_dev:127.0.0.1:45871"
    conn.state = ConnectionState.CONNECTED

    bs = MagicMock()
    bs.start_private_broadcast = AsyncMock()
    bs.stop_private_broadcast = AsyncMock()
    bs.broadcast = AsyncMock()

    cs = MagicMock()
    cs.accept_connection = AsyncMock(return_value=conn)
    cs.device = Device(id="my_dev", name="My Device", hostname="mbox", ip="127.0.0.1", port=45871, os="Linux")

    screen = BroadcastScreen(broadcast_service=bs, connection_service=cs)

    class MockApp(App):
        def __init__(self, screen):
            super().__init__()
            self._screen = screen

        def on_mount(self):
            self.push_screen(self._screen)

    app = MockApp(screen)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Accept connection
        worker = screen._accept_connection(dev)
        await worker.wait()
        await pilot.pause()
        # Ensure screen changed to ConnectedScreen
        assert isinstance(pilot.app.screen, ConnectedScreen)
        assert pilot.app.screen.query_one("#btn-disconnect") is not None



