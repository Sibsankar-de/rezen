from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Footer, Header


class BaseLayout(Container):
    """Base layout of the UI containing centered Header, main content area, and Footer."""

    def __init__(self, *children, **kwargs):
        super().__init__(**kwargs)
        self._initial_children = children

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Container(id="main-viewport"):
            yield from self._initial_children
        yield Footer()
