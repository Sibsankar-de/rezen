import asyncio
import sys
from pathlib import Path

src_dir = Path(__file__).resolve().parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from cli.main import cli


def main() -> None:
    """Primary application entry point which starts src/cli/main.py."""
    asyncio.run(cli())


if __name__ == "__main__":
    main()
