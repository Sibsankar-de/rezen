from protocol.protocol import RLP

class Connector:
    """TCP Connector class for managing connections to devices."""

    def __init__(self, port: int = RLP.DEFAULT_PORT):
        self._port = port

        self._running = False
