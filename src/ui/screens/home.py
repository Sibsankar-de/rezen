from textual.app import ComposeResult
from textual.containers import Center, Middle, Vertical
from textual.screen import Screen
from textual.widgets import Label

from ..layout import BaseLayout


class HomeScreen(Screen):
    """Home screen displaying the Welcome to Rezen message."""

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
