import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from cli.broadcast import run_cli_broadcast
from cli.discover import run_cli_discover
from cli.main import cli
from cli.parser import build_parser
from models.device import Device


def test_build_parser():
    parser = build_parser()
    args = parser.parse_args(["--start-broadcast", "-i", "3.0"])
    assert args.start_broadcast is True
    assert args.interval == 3.0

    args_disc = parser.parse_args(["--start-discover", "-t", "4.0", "-i", "5.0"])
    assert args_disc.start_discover is True
    assert args_disc.timeout == 4.0
    assert args_disc.interval == 5.0


def test_cli_default_launches_tui():
    with patch("ui.app.RezenApp.run") as mock_app_run:
        cli([])
        mock_app_run.assert_called_once()


def test_cli_start_broadcast_flag():
    with patch("cli.main.run_cli_broadcast") as mock_broadcast:
        cli(["--start-broadcast", "--interval", "1.5"])
        mock_broadcast.assert_called_once_with(interval=1.5)


def test_cli_start_discover_flag():
    with patch("cli.main.run_cli_discover") as mock_discover:
        cli(["--start-discover", "--timeout", "3.5", "--interval", "4.5"])
        mock_discover.assert_called_once_with(timeout=3.5, interval=4.5)



def test_run_cli_discover_continuous_interrupt():
    with patch("cli.discover.DiscoveryService") as MockDiscoveryService, \
         patch("cli.discover.DeviceService") as MockDeviceService, \
         patch("time.sleep", side_effect=KeyboardInterrupt):
        
        mock_dev_service = MagicMock()
        mock_dev_service.get_current_device.return_value = Device(
            id="local", name="Local", hostname="host", ip="127.0.0.1", port=45871, os="Linux"
        )
        MockDeviceService.return_value = mock_dev_service

        mock_disc_service = MagicMock()
        mock_disc_service.discover_devices.return_value = []
        MockDiscoveryService.return_value = mock_disc_service

        run_cli_discover(timeout=1.0, interval=2.0)
        mock_disc_service.discover_devices.assert_called_once_with(timeout=1.0)



def test_run_cli_broadcast_interrupt():
    with patch("cli.broadcast.BroadcastService") as MockBroadcastService, \
         patch("cli.broadcast.DeviceService") as MockDeviceService, \
         patch("time.sleep", side_effect=KeyboardInterrupt):
        
        mock_dev_service = MagicMock()
        mock_dev_service.get_current_device.return_value = Device(
            id="local", name="Local", hostname="host", ip="127.0.0.1", port=45871, os="Linux"
        )
        MockDeviceService.return_value = mock_dev_service

        mock_bc_service = MagicMock()
        MockBroadcastService.return_value = mock_bc_service

        run_cli_broadcast(interval=2.0)

        mock_bc_service.start_private_broadcast.assert_called_once()
        mock_bc_service.broadcast.assert_called_once()
        mock_bc_service.stop_private_broadcast.assert_called_once()

