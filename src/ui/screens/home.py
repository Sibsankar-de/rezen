from textual.app import ComposeResult
from textual.containers import Center, Middle, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label

from ..layout import BaseLayout


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
            self.app.push_screen("broadcast")
        elif event.button.id == "btn-discover":
            self.app.push_screen("discover")
