"""Readers turn an input file into a list of Blocks."""

from collections.abc import Callable
from pathlib import Path

from autoflashcards.models import Block
from autoflashcards.readers.markdown import read_markdown
from autoflashcards.readers.pdf import read_pdf

READERS = {
    ".md": read_markdown,
    ".markdown": read_markdown,
    ".pdf": read_pdf,
}


def read(path: Path, progress: Callable[[int, int], None] | None = None) -> list[Block]:
    """`progress(done, total)` is called after each page of a PDF; Markdown is read at once."""
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        raise ValueError(f"unsupported file type: {path.name}")
    return reader(path, progress) if reader is read_pdf else reader(path)
