from textual.app import ComposeResult
from textual.containers import Center, Middle, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label

from container import container
from utils.logger import get_logger
from .broadcast import BroadcastScreen
from .discover import DiscoverScreen
from ..layout import BaseLayout

logger = get_logger(__name__)


class HomeScreen(Screen):
    """Home screen displaying main welcome card and options to broadcast or discover devices."""

    def compose(self) -> ComposeResult:
        with BaseLayout():
            with Center():
                with Middle():
                    with Vertical(id="welcome-card"):
                        yield Label("Welcome to Rezen", id="welcome-title")
                        yield Label(
                            "Remote Device & Screen Control Tool",
                            id="welcome-subtitle",
                        )
                        with Vertical(id="home-options"):
                            yield Button(
                                "📡 Start broadcasting",
                                id="btn-broadcast",
                                variant="primary",
                            )
                            yield Button(
                                "🔍 Discover devices",
                                id="btn-discover",
                                variant="success",
                            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-broadcast":
            logger.info("User navigating to BroadcastScreen.")
            self.app.push_screen(
                BroadcastScreen(
                    broadcast_service=container.broadcast_service(),
                    connection_service=container.connection_service,
                    device_service=container.device_service,
                    screen_cast_service=container.screen_cast_service,
                )
            )
        elif event.button.id == "btn-discover":
            logger.info("User navigating to DiscoverScreen.")
            self.app.push_screen(
                DiscoverScreen(
                    discovery_service=container.discovery_service(),
                    connection_service=container.connection_service,
                    device_service=container.device_service,
                    screen_cast_service=container.screen_cast_service,
                )
            )
