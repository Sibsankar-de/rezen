import pytest
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

        await pilot.click("#btn-back")
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
