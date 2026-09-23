import sys
from pathlib import Path
from typing import Optional

src_dir = Path(__file__).resolve().parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from cli.broadcast import run_cli_broadcast
from cli.discover import run_cli_discover
from cli.parser import build_parser


async def cli(args: Optional[list[str]] = None) -> None:
    """CLI entry point for Rezen."""
    parser = build_parser()
    parsed_args = parser.parse_args(args)

    if parsed_args.start_broadcast:
        await run_cli_broadcast(interval=parsed_args.interval)
    elif parsed_args.start_discover:
        await run_cli_discover(
            timeout=parsed_args.timeout,
            interval=parsed_args.interval if parsed_args.interval != 2.0 else 3.0,
        )
    else:
        from ui.app import RezenApp

        app = RezenApp()
        await app.run_async()


if __name__ == "__main__":
    import asyncio
    asyncio.run(cli())
