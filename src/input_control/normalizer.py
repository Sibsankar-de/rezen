from pynput.keyboard import Key, KeyCode

from utils.logger import get_logger

logger = get_logger(__name__)


class KeyNormalizer:
    @staticmethod
    def normalize_key(key: Key | KeyCode | None) -> str:
        """Convert a pynput key into a serializable identifier."""

        if isinstance(key, Key):
            return f"special:{key.name}"

        if isinstance(key, KeyCode):
            if key.vk is not None:
                return f"vk:{key.vk}"

            # Fallback for character-only keys.
            if key.char is not None:
                return f"char:{key.char}"

        logger.warning(f"Unsupported key: {key!r}")

    @staticmethod
    def denormalize_key(name: str) -> Key | KeyCode | None:
        """Convert a normalized identifier into a pynput key."""

        kind, value = name.split(":", 1)

        if kind == "special":
            return Key[value]

        if kind == "vk":
            return KeyCode.from_vk(int(value))

        if kind == "char":
            return KeyCode.from_char(value)

        logger.warning(f"Unknown key identifier: {name}")
