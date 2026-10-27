"""Heuristic card rules. Each rule maps one Block to zero or more Cards.

Rules are tried in the order of RULES; the first one that makes cards from a block wins,
so one fact doesn't become two cards.
"""

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

# "X is a / are the / was an / is defined as / is called / refers to Y". Not "means": too
# often a plain verb or a name ("proc means")
_DEFINING_VERB = r"(?:is|are|was|were)\s+(?:a|an|the|defined\s+as|called|known\s+as)|refers?\s+to"
_DEFINITION = re.compile(
    r"^(?=[A-Z])(?P<article>(?:the|a|an)\s+)?"  # a real sentence start, not a fragment
    r"(?P<term>[^\s,;:]+(?:\s+[^\s,;:]+){0,4}?)\s+"  # up to 5 words, no commas
    rf"(?P<verb>{_DEFINING_VERB})\s+(?P<rest>\S+\s+\S.*)$",  # at least 2 words after
    re.IGNORECASE,
)
# Words that mean a sentence subject points elsewhere instead of naming a term
_NOT_SUBJECTS = {
    "it", "this", "that", "these", "those", "there", "here", "they", "he", "she", "we",
    "you", "i", "what", "which", "who", "one", "each", "all", "some", "most", "many",
    "such", "its", "their", "his", "her", "our",
}  # fmt: skip
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")
_MAX_SENTENCE_CHARS = 300


def _card(block: Block, front: str, back: str, rule: str, kind: str = "basic") -> Card:
    return Card(front, back, rule, block.source, block.heading_path, block.page, kind)


def _is_term(term: str) -> bool:
    return (
        any(ch.isalpha() for ch in term)  # not a bare number such as a bold page number
        and len(term.split()) <= _MAX_TERM_WORDS
        and term.lower() not in _NOT_TERMS
        and not _CAPTION.match(term)
    )


def term_colon(block: Block) -> list[Card]:
    """`Osmosis: movement of water…` → Osmosis / movement of water…"""
    if block.kind == "heading":
        return []
    match = _TERM_COLON.match(block.text)
    if not match or not _is_term(term := match["term"].strip()):
        return []
    return [_card(block, term, match["definition"].strip(), "term_colon")]


def bold_lead(block: Block) -> list[Card]:
    """`**Mitosis** divides a cell into two…` → Mitosis / divides a cell into two…"""
    lead = block.bold_lead
    if block.kind == "heading" or not lead or lead == block.text:
        return []
    rest = block.text[len(lead) :].strip()
    if rest.startswith(":"):  # "**Term**: definition" is term_colon's
        return []
    term = lead.rstrip(" :-–—,.")
    rest = rest.lstrip(" -–—,.")
    if not _is_term(term) or len(rest.split()) < 3:
        return []
    return [_card(block, term, rest, "bold_lead")]


def definition_sentence(block: Block) -> list[Card]:
    """`A ribosome is a structure that…` → cloze: A {{c1::ribosome}} is a structure that…"""
    if block.kind == "heading":
        return []
    cards = []
    for sentence in _SENTENCE_END.split(block.text):
        match = _DEFINITION.match(sentence)
        if not match or len(sentence) > _MAX_SENTENCE_CHARS:
            continue
        term = match["term"]
        if any(word.lower() in _NOT_SUBJECTS for word in term.split()):
            continue
        start, end = match.span("term")
        cloze = f"{sentence[:start]}{{{{c1::{term}}}}}{sentence[end:]}"
        cards.append(_card(block, cloze, "", "definition_sentence", "cloze"))
    return cards


RULES: dict[str, Callable[[Block], list[Card]]] = {
    "term_colon": term_colon,
    "bold_lead": bold_lead,
    "definition_sentence": definition_sentence,
}


def _in_references(block: Block) -> bool:
    return any(h.lower() in _REFERENCE_HEADINGS for h in block.heading_path)


def generate(blocks: list[Block], rule_names: list[str] | None = None) -> list[Card]:
    """Cards from every block, using the named rules (default: all) in RULES order."""
    rules = [rule for name, rule in RULES.items() if rule_names is None or name in rule_names]
    cards = []
    for block in blocks:
        if _in_references(block):
            continue
        for rule in rules:
            if made := rule(block):
                cards += made
                break
    return cards
