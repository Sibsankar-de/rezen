from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Optional


class ChunkType(StrEnum):
    VIDEO = "video"


class FlagType(StrEnum):
    START_CHUNK = "start_chunk"
    END_CHUNK = "end_chunk"
    MEDIATE_CHUNK = "mediate_chunk"


@dataclass
class StreamChunk:
    frame_id: str
    chunk_id: str

    type: ChunkType
    flag: FlagType

    size: int
    total_chunks: int

    data: bytes
