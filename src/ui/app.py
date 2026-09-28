from pathlib import Path
from textual.app import App
from textual.binding import Binding

from container import container
from utils.logger import get_logger
from .screens import HomeScreen

STYLES_DIR = Path(__file__).parent / "styles"

logger = get_logger(__name__)


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

    async def on_mount(self) -> None:
        """Start shared network services and route to the home screen."""
        logger.info("Rezen UI starting up.")
        try:
            await container.start()
        except Exception:
            logger.error("Failed to start shared network services.", exc_info=True)
            raise
        self.push_screen("home")

    async def on_unmount(self) -> None:
        """Tear down shared network services on app exit."""
        logger.info("Rezen UI shutting down.")
        await container.stop()


if __name__ == "__main__":
    app = RezenApp()
    app.run()
