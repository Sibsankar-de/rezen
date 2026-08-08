from models.device import Device


class DeviceRegistry:
    _devices: dict[str, Device]

    def __init__(self):
        self._devices = {}

    def upsert(self, device: Device):
        self._devices[device.id] = device

    def get(self, device_id: str) -> Device | None:
        return self._devices.get(device_id)

    def remove(self, device_id: str):
        if device_id in self._devices:
            del self._devices[device_id]

    def list_devices(self) -> list[Device]:
        return list(self._devices.values())

    def clear(self):
        self._devices.clear()
