try:
    import evdev
    from evdev import ecodes
except ImportError:
    evdev = None
    ecodes = None

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
            # Prioritize character representation (e.g. 'a', '1')
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

    @staticmethod
    def normalize_evdev_key(code: int) -> str | None:
        """Convert a Linux evdev key code to an identifier using ecodes."""
        if ecodes is None:
            return None
        name = ecodes.KEY.get(code)
        if isinstance(name, list):
            name = name[0]
        if not name or not name.startswith("KEY_"):
            return None

        val = name[4:].lower()
        if len(val) == 1:
            return f"char:{val}"

        # Standardize modifier names to match pynput format (e.g. shift, shift_r, cmd)
        if val.startswith("left"):
            base = val[4:]
            val = "cmd" if base == "meta" else base
        elif val.startswith("right"):
            base = val[5:]
            val = "cmd_r" if base == "meta" else f"{base}_r"

        return f"special:{val}"

    @staticmethod
    def denormalize_to_evdev(name: str) -> int | None:
        """Convert a key identifier into a Linux evdev key code using ecodes."""
        if not name or ecodes is None:
            return None

        # Direct evdev name e.g. "KEY_A", "KEY_ENTER"
        if name.upper().startswith("KEY_"):
            return ecodes.ecodes.get(name.upper())

        # Extract value from kind:value format
        _, _, value = name.partition(":")
        val = (value or name).upper().replace("CMD", "META")

        # Direct match with KEY_ prefix (e.g. KEY_A, KEY_ENTER, KEY_SPACE)
        code = ecodes.ecodes.get(f"KEY_{val}")
        if code is not None:
            return code

        # Right modifiers (e.g. SHIFT_R -> KEY_RIGHTSHIFT)
        if val.endswith("_R"):
            return ecodes.ecodes.get(f"KEY_RIGHT{val[:-2]}")

        # Left/generic modifiers (e.g. SHIFT -> KEY_LEFTSHIFT)
        return ecodes.ecodes.get(f"KEY_LEFT{val.removesuffix('_L')}")
