from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static


class BaseLayout(Container):
    """Base layout of the UI containing centered main content area and slim footer bar."""

    def __init__(self, *children, **kwargs):
        super().__init__(*children, **kwargs)
        self._initial_children = children

    def compose(self) -> ComposeResult:
        yield from self._initial_children
        yield Static(" [Ctrl+Q] Quit", id="footer-bar")
