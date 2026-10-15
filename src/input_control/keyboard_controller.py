from pynput.keyboard import Controller

from models.input import InputObject
from input_control.normalizer import KeyNormalizer
from utils.logger import get_logger

logger = get_logger(__name__)


class KeyboardController:
    """Apply keyboard events on the screen"""

    def __init__(self):
        self._keyboard_controller = Controller()

    def apply(self, input_object: InputObject) -> None:
        """Apply key set"""
        denorm_keys = [KeyNormalizer.denormalize_key(key) for key in input_object.data]

        for key in denorm_keys:
            try:
                if key is not None:
                    self._keyboard_controller.press(key)
            except Exception:
                logger.error(f"Failed to apply key {key}", exc_info=True)
                break

        # release keys
        for key in reversed(denorm_keys):
            try:
                if key is not None:
                    self._keyboard_controller.release(key)
            except Exception:
                pass
