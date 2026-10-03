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

setup_logging()
logger = get_logger(__name__)


def main() -> None:
    """Primary application entry point which starts src/cli/main.py."""
    logger.info("Starting rezen.")

    asyncio.run(cli())

    logger.info("Stopping rezen.")


if __name__ == "__main__":
    main()
