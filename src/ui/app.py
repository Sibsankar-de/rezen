from pathlib import Path
from textual.app import App
from textual.binding import Binding

from .screens.home import HomeScreen

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

    SCREENS = {
        "home": HomeScreen,
    }

    def on_mount(self) -> None:
        """Initial routing to the home screen."""
        self.push_screen("home")


if __name__ == "__main__":
    app = RezenApp()
    app.run()
