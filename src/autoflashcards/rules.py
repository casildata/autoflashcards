"""Heuristic card rules. Each rule maps one Block to zero or more Cards."""

import re
from collections.abc import Callable

from autoflashcards.models import Block, Card

# "Term: definition" with a short term and a space after the colon (skips URLs and times)
_TERM_COLON = re.compile(r"^(?P<term>[^:]{1,60}?)\s*:\s+(?P<definition>\S.*)$")
_MAX_TERM_WORDS = 6
# Labels that look like "Term:" but introduce a remark, not a definition
_NOT_TERMS = {
    "note", "notes", "example", "examples", "e.g.", "tip", "warning", "see", "source",
    "keywords", "key words", "abstract",
}  # fmt: skip
_CAPTION = re.compile(r"^(fig(ure)?|table|chart|exhibit|eq(uation)?)\.?\s*\d", re.IGNORECASE)
# Sections whose lines are citations, not facts
_REFERENCE_HEADINGS = {"references", "bibliography", "works cited", "sources"}


def term_colon(block: Block) -> list[Card]:
    if block.kind == "heading":
        return []
    match = _TERM_COLON.match(block.text)
    if not match:
        return []
    term = match["term"].strip()
    if len(term.split()) > _MAX_TERM_WORDS or term.lower() in _NOT_TERMS or _CAPTION.match(term):
        return []
    return [
        Card(
            term,
            match["definition"].strip(),
            "term_colon",
            block.source,
            block.heading_path,
            block.page,
        )
    ]


RULES: dict[str, Callable[[Block], list[Card]]] = {
    "term_colon": term_colon,
}


def _in_references(block: Block) -> bool:
    return any(h.lower() in _REFERENCE_HEADINGS for h in block.heading_path)


def generate(blocks: list[Block]) -> list[Card]:
    return [
        card
        for block in blocks
        if not _in_references(block)
        for rule in RULES.values()
        for card in rule(block)
    ]
