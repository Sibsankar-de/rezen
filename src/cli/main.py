import sys
from pathlib import Path
from typing import Optional

# Ensure src directory is in sys.path when running CLI
src_dir = Path(__file__).resolve().parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from cli.broadcast import run_cli_broadcast
from cli.discover import run_cli_discover
from cli.parser import build_parser


def cli(args: Optional[list[str]] = None) -> None:
    """CLI entry point for Rezen."""
    parser = build_parser()
    parsed_args = parser.parse_args(args)

    if parsed_args.start_broadcast:
        run_cli_broadcast(interval=parsed_args.interval)
    elif parsed_args.start_discover:
        run_cli_discover(
            timeout=parsed_args.timeout,
            interval=parsed_args.interval if parsed_args.interval != 2.0 else 3.0,
        )
    else:
        from ui.app import RezenApp

        app = RezenApp()
        app.run()




if __name__ == "__main__":
    cli()
