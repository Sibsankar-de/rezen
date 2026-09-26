from pathlib import Path
from textual.app import App
from textual.binding import Binding

from services.connection_service import ConnectionService
from .screens import BroadcastScreen, DiscoverScreen, HomeScreen

STYLES_DIR = Path(__file__).parent / "styles"


class RezenApp(App):
    """Entry point of the Rezen UI containing textual routing and TCSS styling."""

    TITLE = "Rezen"

    CSS_PATH = [
        STYLES_DIR / "app.tcss",
        STYLES_DIR / "screens.tcss",
        STYLES_DIR / "widgets.tcss",
    ]

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
    ]

    # HomeScreen has no constructor args so it can stay in SCREENS.
    # BroadcastScreen and DiscoverScreen need a shared ConnectionService,
    # so they are pushed imperatively (see on_button_pressed in HomeScreen).
    SCREENS = {
        "home": HomeScreen,
    }

    def on_mount(self) -> None:
        """Create the shared connection service and route to the home screen."""
        self.connection_service = ConnectionService()
        self.push_screen("home")


if __name__ == "__main__":
    app = RezenApp()
    app.run()
