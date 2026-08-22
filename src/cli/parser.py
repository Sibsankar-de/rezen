import argparse


def build_parser() -> argparse.ArgumentParser:
    """Construct and configure the argument parser for Rezen CLI."""
    parser = argparse.ArgumentParser(
        prog="rezen",
        description="Rezen - Remote Device & Screen Control CLI",
    )
    parser.add_argument(
        "--start-broadcast",
        "-b",
        action="store_true",
        help="Start continuous background LAN presence broadcasting with logs (without TUI)",
    )
    parser.add_argument(
        "--start-discover",
        "-d",
        action="store_true",
        help="Start continuous LAN device discovery with periodic scanning logs (without TUI)",
    )
    parser.add_argument(
        "--interval",
        "-i",
        type=float,
        default=2.0,
        help="Interval in seconds between broadcast heartbeats or discovery scans (default: 2.0s for broadcast, 3.0s for discovery)",
    )
    parser.add_argument(
        "--timeout",
        "-t",
        type=float,
        default=2.0,
        help="Discovery scan timeout in seconds (default: 2.0)",
    )
    return parser


