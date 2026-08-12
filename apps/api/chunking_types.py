"""Shared chunker output type (roadmap step 098, promoted out of
chunking_fixed_size.py in step 099 once a second chunker needed the
identical shape -- same "build inline for the first consumer, promote
once a second one needs it" pattern extraction_tables.py's
rows_to_markdown already used for the extraction side of this
pipeline).
"""

from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    start: int
    end: int
    index: int
