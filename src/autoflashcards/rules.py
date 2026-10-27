"""Heuristic card rules. Each rule maps one Block to zero or more Cards."""

import re
from collections.abc import Callable

from autoflashcards.models import Block, Card

# "Term: definition" with a short term and a space after the colon (skips URLs and times)
_TERM_COLON = re.compile(r"^(?P<term>[^:]{1,60}?)\s*:\s+(?P<definition>\S.*)$")
_MAX_TERM_WORDS = 6
# Labels that look like "Term:" but introduce a remark, not a definition
_NOT_TERMS = {"note", "notes", "example", "examples", "e.g.", "tip", "warning", "see", "source"}


def term_colon(block: Block) -> list[Card]:
    if block.kind == "heading":
        return []
    match = _TERM_COLON.match(block.text)
    if not match:
        return []
    term = match["term"].strip()
    if len(term.split()) > _MAX_TERM_WORDS or term.lower() in _NOT_TERMS:
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


def generate(blocks: list[Block]) -> list[Card]:
    return [card for block in blocks for rule in RULES.values() for card in rule(block)]
