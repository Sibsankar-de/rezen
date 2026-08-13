import platform
import secrets
import socket
import string
from typing import Optional

from db.repository import SettingsRepository
from models.device import Device
from protocol.protocol import RLP
from utils.logger import get_logger

logger = get_logger(__name__)


def generate_device_id(length: int = 10) -> str:
    """Generate a random alphanumeric ID of specified length (default 10 characters)."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_local_ip() -> str:
    """Helper function to obtain the primary local IP address of this device."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


class DeviceService:
    """Service responsible for constructing and managing local device metadata."""

    def __init__(self):
        self.settings_repo = SettingsRepository()

    def get_current_device(self) -> Device:
        """Return a Device object representing the current host device."""
        device_id = self.settings_repo.get_setting("device_id")
        if not device_id:
            device_id = generate_device_id(10)
            self.settings_repo.set_setting("device_id", device_id)

        device = Device(
            id=device_id,
            name=socket.gethostname(),
            hostname=socket.gethostname(),
            ip=get_local_ip(),
            port=RLP.DEFAULT_PORT,
            os=platform.system(),
        )
        logger.debug(f"Retrieved current device: {device}")
        return device
