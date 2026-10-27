"""Readers turn an input file into a list of Blocks."""

from pathlib import Path

from autoflashcards.models import Block
from autoflashcards.readers.markdown import read_markdown

READERS = {
    ".md": read_markdown,
    ".markdown": read_markdown,
}


def read(path: Path) -> list[Block]:
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        raise ValueError(f"unsupported file type: {path.name}")
    return reader(path)
