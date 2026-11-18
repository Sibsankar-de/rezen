import asyncio
import sys
from pathlib import Path
from utils.logger import setup_logging, get_logger
from utils.multiprocessing_fix import apply_multiprocessing_fix

src_dir = Path(__file__).resolve().parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

apply_multiprocessing_fix()
from cli.main import cli
from cli.parser import build_parser

logger = get_logger(__name__)

INFO_FLAGS = ["-v", "--version", "-h", "--help"]


def main() -> None:
    """Primary application entry point which starts src/cli/main.py."""
    if any(arg in sys.argv for arg in INFO_FLAGS):
        parser = build_parser()
        parser.parse_args()

    setup_logging()
    logger.info("Starting rezen.")

    asyncio.run(cli())

    logger.info("Stopping rezen.")


if __name__ == "__main__":
    main()
