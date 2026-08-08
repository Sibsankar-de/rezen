class RLP:
    """
    Rezen LAN Protocol (RLP)
    """

    NAME = "RLP"
    VERSION = 1
    DEFAULT_PORT = 45871
    BROADCAST_IP = "255.255.255.255"
    MAX_PACKET_SIZE = 64 * 1024
    DISCOVERY_INTERVAL = 5
    DEVICE_TIMEOUT = 20
