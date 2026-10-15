from pynput.keyboard import Key, KeyCode

from utils.logger import get_logger

logger = get_logger(__name__)


class KeyNormalizer:
    @staticmethod
    def normalize_key(key: Key | KeyCode | None) -> str | None:
        """Convert a pynput key into a serializable identifier."""

        if isinstance(key, Key):
            return f"special:{key.name}"

        if isinstance(key, KeyCode):
            # Prioritize character representation (e.g. 'a', '1', '@')
            if key.char is not None:
                return f"char:{key.char}"

            # Fallback for virtual key codes without char
            if key.vk is not None:
                return f"vk:{key.vk}"

        logger.warning(f"Unsupported key: {key!r}")
        return None

    @staticmethod
    def denormalize_key(name: str) -> Key | KeyCode | None:
        """Convert a normalized identifier into a pynput key."""
        if not name or ":" not in name:
            logger.warning(f"Malformed key identifier: {name}")
            return None

        kind, value = name.split(":", 1)

        if kind == "special":
            try:
                return Key[value]
            except KeyError:
                logger.warning(f"Unknown special key: {value}")
                return None

        if kind == "vk":
            try:
                return KeyCode.from_vk(int(value))
            except ValueError:
                logger.warning(f"Invalid vk value: {value}")
                return None

        if kind == "char":
            return KeyCode.from_char(value)

        logger.warning(f"Unknown key identifier: {name}")
        return None
