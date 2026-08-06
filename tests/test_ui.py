import pytest
from ui.app import RezenApp
from ui.layout import BaseLayout
from ui.screens.home import HomeScreen


@pytest.mark.asyncio
async def test_rezen_app_mounts_home_screen():
    app = RezenApp()
    async with app.run_test() as pilot:
        assert isinstance(pilot.app.screen, HomeScreen)
        assert pilot.app.screen.query_one(BaseLayout) is not None
        assert pilot.app.screen.query_one("#welcome-card") is not None
        assert pilot.app.screen.query_one("#welcome-title") is not None
        assert pilot.app.screen.query_one("#welcome-subtitle") is not None
