import pytest
from unittest.mock import patch

from main import main


@pytest.mark.asyncio
async def test_main_calls_cli():
    with patch("main.cli") as mock_cli:
        await main()
        mock_cli.assert_called_once()
