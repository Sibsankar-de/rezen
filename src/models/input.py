from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Optional


class InputType(StrEnum):
    KEYBOARD = "keyboard"
    MOUSE = "mouse"


@dataclass
class InputObject:
    type: InputType
    data: set[str]
