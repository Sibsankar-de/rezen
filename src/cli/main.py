import sys
from pathlib import Path

# Ensure src directory is in sys.path when running CLI
src_dir = Path(__file__).resolve().parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from ui.app import RezenApp


def cli() -> None:
    """CLI entry point for Rezen."""
    app = RezenApp()
    app.run()


if __name__ == "__main__":
    cli()
