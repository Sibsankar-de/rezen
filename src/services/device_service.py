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


import psutil


def generate_device_id(length: int = 10) -> str:
    """Generate a random alphanumeric ID of specified length (default 10 characters)."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_local_ip() -> str:
    """Helper function to obtain the primary local IP address of this device."""
    # 1. Try connecting to external DNS or gateway (fast UDP check without sending traffic)
    for test_ip in ("8.8.8.8", "1.1.1.1"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.2)
            s.connect((test_ip, 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            pass

    # 2. Inspect active network interfaces via psutil (essential for offline Wi-Fi LANs)
    try:
        interfaces = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        candidates = []
        for iface_name, addrs in interfaces.items():
            stat = stats.get(iface_name)
            if stat and not stat.isup:
                continue
            is_virtual = any(
                v in iface_name.lower()
                for v in ("docker", "br-", "veth", "virbr", "vmnet")
            )
            for addr in addrs:
                if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                    candidates.append((not is_virtual, addr.address))
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]
    except Exception:
        pass

    try:
        ip = socket.gethostbyname(socket.gethostname())
        if not ip.startswith("127."):
            return ip
    except Exception:
        pass

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
