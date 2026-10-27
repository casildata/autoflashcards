"""Data passed between pipeline stages: readers make Lines or Blocks, rules make Cards."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Line:
    """One line of text as laid out on a page (PDF only; structure.py turns these into Blocks)."""

    text: str
    page: int  # 1-based
    size: float  # font size in points
    bold: bool  # every character is in a bold font
    x0: float
    top: float  # distance from the top of the page
    bottom: float
    bold_lead: str = ""  # bold text at the start of the line, after any bullet marker
    x1: float | None = None  # where the line ends
    box_right: float | None = None  # right edge of the text box the line sits in


@dataclass(frozen=True)
class Block:
    kind: Literal["heading", "bullet", "paragraph"]
    text: str
    source: str  # file name, shown on the card
    heading_path: tuple[str, ...] = ()  # headings above this block, outermost first
    page: int | None = None  # 1-based; None for formats without pages
    bold_lead: str = ""  # bold text that starts the block, e.g. a term being defined


@dataclass(frozen=True)
class Card:
    front: str  # for cloze cards, the full text with {{c1::...}} markup
    back: str  # empty for cloze cards
    rule: str  # name of the rule that made the card
    source: str
    heading_path: tuple[str, ...] = ()
    page: int | None = None
    kind: Literal["basic", "cloze"] = "basic"

    @property
    def source_label(self) -> str:
        """Where the card came from, e.g. `notes.pdf · p.12 · Cells › Transport`."""
        parts = [self.source]
        if self.page is not None:
            parts.append(f"p.{self.page}")
        if self.heading_path:
            parts.append(" › ".join(self.heading_path))
        return " · ".join(parts)


def normalize(text: str) -> str:
    """Case- and whitespace-insensitive form, used for card IDs and duplicate checks."""
    return " ".join(text.lower().split())
