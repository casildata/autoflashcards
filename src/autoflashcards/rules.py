"""Heuristic card rules.

Each rule looks at one block, `blocks[i]`, and may read the blocks after it (a slide title's
bullets, a bold term's sub-bullets). Rules are tried in the order of RULES; the first one
that makes cards from a block wins, so one fact doesn't become two cards.
"""

import re
from collections.abc import Callable

from autoflashcards.models import Block, Card

# "Term: definition", also with "=", "→" or "->" as on slides. A colon needs a space after
# it, which skips URLs and times
_TERM_SEPARATOR = re.compile(
    r"^(?P<term>[^:=→]{1,60}?)\s*(?::\s+|=\s*|→\s*|->\s*)(?P<definition>\S.*)$"
)
_MAX_TERM_WORDS = 6
# Labels that look like "Term:" but introduce a remark, not a definition
_NOT_TERMS = {
    "note", "notes", "example", "examples", "e.g.", "tip", "warning", "see", "source",
    "keywords", "key words", "abstract", "e-mail", "email", "tel", "phone", "fax", "doi",
}  # fmt: skip
_CAPTION = re.compile(r"^(fig(ure)?|table|chart|exhibit|eq(uation)?)\.?\s*\d", re.IGNORECASE)
# Sections with no facts to learn: citations, slide-deck front and back matter
_SKIP_SECTIONS = {
    "references", "bibliography", "works cited", "sources", "table of contents", "contents",
    "thanks", "thank you", "questions", "credits", "acknowledgements", "acknowledgments",
}  # fmt: skip
# Slide titles that describe a picture rather than name a term
_PICTURE_TITLE = re.compile(
    r"^(image|illustration|example|diagram|figure|photo|picture|video)s?\b", re.IGNORECASE
)
MAX_SECTION_BULLETS = 8  # a slide's worth; longer bullet lists are textbook lists, not slides
MAX_BACK_BULLETS = 3
MAX_BULLET_WORDS = 20

# "X is a / are the / was an / is defined as / is called / refers to / means Y". "means" only
# before a noun phrase or "-ing" word, so a name such as "proc means and…" doesn't count
_DEFINING_VERB = (
    r"(?:is|are|was|were)\s+(?:a|an|the|defined\s+as|called|known\s+as)|refers?\s+to"
    r"|means(?=\s+(?:a|an|the|that|\w+ing)\b)"
)
_DEFINITION_BODY = (
    r"(?P<article>(?:the|a|an)\s+)?"
    r"(?P<term>[^\s,;:]+(?:\s+[^\s,;:]+){0,4}?)\s+"  # up to 5 words, no commas
    rf"(?P<verb>{_DEFINING_VERB})\s+(?P<rest>\S+\s+\S.*)$"  # at least 2 words after
)
# a real sentence start, not a fragment: (?-i:) keeps the capital check case-sensitive
_DEFINITION = re.compile(r"^(?=(?-i:[A-Z]))" + _DEFINITION_BODY, re.IGNORECASE)
# a later clause, after "; " or ", and ": "X means A, and Y means B"
_CLAUSE_DEFINITION = re.compile("^" + _DEFINITION_BODY, re.IGNORECASE)
_CLAUSE_BREAK = re.compile(r",\s+(?:and|while|whereas)\s+|;\s+")
# "Retention, the share of customers who return, is…": a term, then a description set off by
# commas, then the sentence goes on
_APPOSITIVE = re.compile(
    r"^(?P<term>(?-i:[A-Z])[\w-]*(?:\s+[\w-]+){0,3}),\s+(?:the|a|an)\s+[^,]{8,150},\s+[a-z]"
)
# Words that open a sentence without naming a term ("However, the…", "In 2010, a…")
_NOT_APPOSITIVE_STARTS = {
    "however", "thus", "therefore", "then", "also", "here", "first", "second", "finally",
    "moreover", "instead", "today", "in", "on", "at", "for", "after", "before", "during",
    "when", "while", "if", "because", "although", "unlike", "like", "as", "by", "with",
    "from", "to", "of",
}  # fmt: skip
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
        and not re.fullmatch(r"\d+s", term)  # nor a decade ("1970s")
        and term.count("(") == term.count(")")  # not cut mid-formula ("18.3 (= 406/22)")
        and len(term.split()) <= _MAX_TERM_WORDS
        and term.lower() not in _NOT_TERMS
        and not _CAPTION.match(term)
    )


def _is_skipped_section(heading: str) -> bool:
    return re.sub(r"[^\w\s]", "", heading.lower()).strip() in _SKIP_SECTIONS


def _all_bold(block: Block) -> bool:
    return bool(block.bold_lead) and block.bold_lead == block.text


def term_colon(block: Block) -> list[Card]:
    """`Osmosis: movement of water…` (or `=`, `→`) → Osmosis / movement of water…"""
    if block.kind == "heading":
        return []
    match = _TERM_SEPARATOR.match(block.text)
    if not match or not _is_term(term := match["term"].strip()):
        return []
    return [_card(block, term, match["definition"].strip(), "term_colon")]


def bold_lead(block: Block) -> list[Card]:
    """`**Mitosis** divides a cell into two…` → Mitosis / divides a cell into two…"""
    lead = block.bold_lead
    if block.kind == "heading" or not lead or _all_bold(block):
        return []
    rest = block.text[len(lead) :].strip()
    if rest.startswith(":"):  # "**Term**: definition" is term_colon's
        return []
    term = lead.rstrip(" :-–—,.")
    rest = rest.lstrip(" -–—,.=→>")
    if not _is_term(term) or len(rest.split()) < 3:
        return []
    return [_card(block, term, rest, "bold_lead")]


def definition_sentence(block: Block) -> list[Card]:
    """`A ribosome is a structure that…` → cloze: A {{c1::ribosome}} is a structure that…

    Also "X means Y", one deletion per defining clause ("X means A, and Y means B" → c1, c2),
    and appositives: `Retention, the share of customers who return, is…`.
    """
    if block.kind == "heading":
        return []
    cards = []
    for sentence in _SENTENCE_END.split(block.text):
        if len(sentence) > _MAX_SENTENCE_CHARS:
            continue
        cloze = sentence
        # from the end, so earlier spans stay valid; numbered c1, c2… in reading order
        spans = _defined_terms(sentence)
        for n, (start, end) in reversed(list(enumerate(spans, start=1))):
            cloze = f"{cloze[:start]}{{{{c{n}::{cloze[start:end]}}}}}{cloze[end:]}"
        if spans:
            cards.append(_card(block, cloze, "", "definition_sentence", "cloze"))
    return cards


def _names_a_term(term: str) -> bool:
    return not any(word.lower() in _NOT_SUBJECTS for word in term.split())


def _defined_terms(sentence: str) -> list[tuple[int, int]]:
    """Where the terms a sentence defines are: one per clause, or one appositive."""
    spans = []
    pattern, start = _DEFINITION, 0
    breaks = [(m.start(), m.end()) for m in _CLAUSE_BREAK.finditer(sentence)]
    for end, next_start in [*breaks, (len(sentence), len(sentence))]:
        match = pattern.match(sentence[start:end])
        if match and _names_a_term(match["term"]):
            spans.append((start + match.start("term"), start + match.end("term")))
        pattern, start = _CLAUSE_DEFINITION, next_start
    if not spans and (match := _APPOSITIVE.match(sentence)):
        term = match["term"]
        if term.split()[0].lower() not in _NOT_APPOSITIVE_STARTS and _names_a_term(term):
            spans.append(match.span("term"))
    return spans


def bold_term_bullets(blocks: list[Block], i: int) -> list[Card]:
    """An all-bold bullet followed by plain bullets that explain it:

    • **Protein kinases**
        • Transfer phosphates from ATP to proteins
    → Protein kinases / Transfer phosphates from ATP to proteins
    """
    term = blocks[i]
    if term.kind != "bullet" or not _all_bold(term) or not _is_term(term.text):
        return []
    explained = []
    for block in blocks[i + 1 :]:
        same_place = (block.heading_path, block.page) == (term.heading_path, term.page)
        if block.kind != "bullet" or _all_bold(block) or not same_place:
            break
        explained.append(block.text)
    if not explained:
        return []
    return [_card(term, term.text, "\n".join(explained[:MAX_BACK_BULLETS]), "bold_term_bullets")]


def _is_bullet(block: Block) -> bool:
    """A bullet, or a line that reads like one: slides whose bullet markers are pictures
    give paragraphs, but short ones without a closing period."""
    if block.kind == "bullet":
        return True
    return (
        block.kind == "paragraph"
        and any(ch.isalpha() for ch in block.text)
        and len(block.text.split()) <= MAX_BULLET_WORDS
        and not re.search(r"[.!?:]$", block.text)
    )


def slide_title_bullets(blocks: list[Block], i: int) -> list[Card]:
    """A slide whose title is a term and whose bullets explain it:

    G protein-coupled receptor (GPCR)
      • Cell-surface receptors that work with a G protein
    → G protein-coupled receptor (GPCR) / Cell-surface receptors that work with a G protein

    Only short, all-bullet sections count, so textbook headings don't become list cards.
    """
    title = blocks[i]
    if (
        title.kind != "heading"
        or not _is_term(title.text)
        or _PICTURE_TITLE.match(title.text)
        or _is_skipped_section(title.text)
    ):
        return []
    section = []
    for block in blocks[i + 1 :]:
        if block.kind == "heading" or block.page != title.page:
            break  # a slide's bullets are on its own page
        section.append(block)
    if (
        not section
        or len(section) > MAX_SECTION_BULLETS
        or not all(_is_bullet(b) for b in section)
        or _all_bold(section[0])  # sub-terms under the title: bold_term_bullets' job
        # labeled items ("Osmosis: …") are cards already; the title is just their category
        or any(term_colon(b) for b in section)
    ):
        return []
    back = "\n".join(b.text for b in section[:MAX_BACK_BULLETS])
    return [_card(section[0], title.text, back, "slide_title_bullets")]


Rule = Callable[[list[Block], int], list[Card]]


def _one_block(rule: Callable[[Block], list[Card]]) -> Rule:
    return lambda blocks, i: rule(blocks[i])


RULES: dict[str, Rule] = {
    "term_colon": _one_block(term_colon),
    "bold_lead": _one_block(bold_lead),
    "definition_sentence": _one_block(definition_sentence),
    "bold_term_bullets": bold_term_bullets,
    "slide_title_bullets": slide_title_bullets,
}


def _skipped(block: Block) -> bool:
    # only the nearest heading: one misread heading mustn't hide the rest of a document
    return bool(block.heading_path) and _is_skipped_section(block.heading_path[-1])


def generate(blocks: list[Block], rule_names: list[str] | None = None) -> list[Card]:
    """Cards from every block, using the named rules (default: all) in RULES order."""
    rules = [rule for name, rule in RULES.items() if rule_names is None or name in rule_names]
    cards = []
    for i, block in enumerate(blocks):
        if _skipped(block):
            continue
        for rule in rules:
            if made := rule(blocks, i):
                cards += made
                break
    return cards
