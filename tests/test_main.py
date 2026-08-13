import pytest
from unittest.mock import patch

from main import main


def test_main_calls_cli():
    with patch("main.cli") as mock_cli:
        main()
        mock_cli.assert_called_once()
