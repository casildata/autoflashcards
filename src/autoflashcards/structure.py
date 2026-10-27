"""Structure stage: page Lines → Blocks (headings, bullets, paragraphs) with heading paths.

Steps: clean text, drop running headers and footers, find headings by font size and weight,
then group the remaining lines into bullets and paragraphs.
"""

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field, replace

from autoflashcards.models import Block, Line

HEADING_SIZE_RATIO = 1.2  # a line this much larger than body text is a heading
MAX_HEADING_WORDS = 15
MAX_BOLD_HEADING_WORDS = 8  # a body-size line that is all bold, short, and unpunctuated
RUNNING_TEXT_SHARE = 0.4  # top/bottom text on this share of pages is a header or footer
MIN_PAGE_BODY_CHARS = 150  # a page with less body text than this uses the document's body size

# The PDF reader writes glyphs it can't map to text as U+FFFD; at the start of a line one is
# almost always a bullet, anywhere else it is dropped
_UNMAPPED = "�"
_BULLET = re.compile(r"^(?:[•●○◦▪■▸►‣⁃–—*�-]|\d{1,2}[.)]|[a-z][.)])\s+(?P<text>.+)$")
_PAGE_NUMBER = re.compile(r"^(page\s*)?\d+(\s*(of|/)\s*\d+)?$", re.IGNORECASE)
_ENDS_SENTENCE = re.compile(r"[.!?:;]$")
# "Cell theory = …", "Ligand → …", "Osmosis: …" opens a new item even right after a line
# that looks wrapped (slide bullets have no periods)
_STARTS_DEFINITION = re.compile(r"^[^:=→]{1,40}?\s*(?::\s|=|→|->)")


def _clean(line: Line) -> Line:
    text = unicodedata.normalize("NFKC", line.text)  # ligatures such as "ﬁ" become "fi"
    if not _BULLET.match(text):
        text = text.replace(_UNMAPPED, "")
    lead = unicodedata.normalize("NFKC", line.bold_lead)
    return replace(line, text=" ".join(text.split()), bold_lead=" ".join(lead.split()))


def _drop_running_text(lines: list[Line]) -> list[Line]:
    """Remove page numbers and running headers/footers: a page's top or bottom line that is
    a bare page number, or that repeats at the same height on many pages."""
    lines = [line for line in lines if line.text]
    pages = {line.page for line in lines}

    tops = defaultdict(list)
    for line in lines:
        tops[line.page].append(line.top)
    edge_tops = {(page, t) for page, ts in tops.items() for t in (min(ts), max(ts))}

    def at_edge(line: Line) -> bool:
        return (line.page, line.top) in edge_tops

    def key(line: Line) -> tuple[str, int]:
        # "Lecture 3 - slide 12" matches "Lecture 3 - slide 13"
        return re.sub(r"\d+", "#", line.text.lower()), round(line.top / 10)

    pages_with = defaultdict(set)
    for line in filter(at_edge, lines):
        pages_with[key(line)].add(line.page)

    def running(line: Line) -> bool:
        # 40%, not half: books alternate left- and right-page headers and footers
        count = len(pages_with[key(line)])
        repeated = count >= 2 and count >= RUNNING_TEXT_SHARE * len(pages)
        return at_edge(line) and (repeated or bool(_PAGE_NUMBER.match(line.text)))

    return [line for line in lines if not running(line)]


def _body_size(lines: list[Line]) -> float:
    """Font size of most of the text, weighted by length."""
    weight = defaultdict(int)
    for line in lines:
        weight[round(line.size, 1)] += len(line.text)
    return max(weight, key=weight.get)


def _page_body_sizes(lines: list[Line]) -> dict[int, float]:
    """Body font size per page. Slide handouts scale each slide differently, so one slide's
    bullets can be larger than another's notes; title and picture slides have too little
    text to tell and use the document's body size."""
    document = _body_size(lines)
    by_page = defaultdict(list)
    for line in lines:
        by_page[line.page].append(line)
    sizes = {}
    for page, page_lines in by_page.items():
        size = _body_size(page_lines)
        chars = sum(len(ln.text) for ln in page_lines if round(ln.size, 1) == size)
        sizes[page] = size if chars >= MIN_PAGE_BODY_CHARS else document
    return sizes


def _is_heading(line: Line, body: float, next_line: Line | None = None) -> bool:
    if not any(ch.isalpha() for ch in line.text):
        return False  # section numbers on divider slides ("11.2", "01")
    words = len(line.text.split())
    if line.size >= body * HEADING_SIZE_RATIO:
        # Large text that reads as prose isn't a heading: on slide handouts a slide's 9pt
        # bullets can be "large" next to another slide's 7pt notes
        sentence_goes_on = (
            not line.bold  # slide titles are bold, and wrap mid-phrase too
            and next_line is not None
            and next_line.text[:1].islower()
            and round(next_line.size) == round(line.size)
            and next_line.box_right == line.box_right
        )
        return (
            words <= MAX_HEADING_WORDS
            and not sentence_goes_on
            and not re.search(r"[.,;]$", line.text)
        )
    return (
        line.bold
        and words <= MAX_BOLD_HEADING_WORDS
        and not _BULLET.match(line.text)
        and not re.search(r"[.:;,]$", line.text)
    )


@dataclass
class _Open:
    """A block still being built from consecutive lines."""

    kind: str
    page: int
    texts: list[str] = field(default_factory=list)
    first: Line | None = None
    last: Line | None = None


def _reaches_box_edge(prev: Line, line: Line) -> bool:
    """Whether `prev` ran out of room: `line`'s first word wouldn't have fit after it.

    A short line followed by a capitalized one is a new item, as on slides whose bullet
    markers are images. Without box information (hand-built Lines) assume it wrapped.
    """
    if prev.x1 is None or prev.box_right is None or not line.text:
        return True
    char_width = (prev.x1 - prev.x0) / max(len(prev.text), 1)
    first_word = len(line.text.split()[0]) + 1  # and the space before it
    return prev.x1 + first_word * char_width >= prev.box_right - char_width


def _continues(block: _Open, line: Line) -> bool:
    """Whether `line` wraps on from the open block rather than starting a new one."""
    prev = block.last
    starts_lower = line.text[:1].islower()
    indented = line.x0 > block.first.x0 + 2
    if block.kind == "bullet" and line.page == prev.page and not (indented or starts_lower):
        return False  # a bullet's wrapped lines are indented past its marker, or mid-sentence
    if line.page != prev.page or line.box_right != prev.box_right or line.top < prev.top:
        return starts_lower  # next page, column or box: only a sentence carrying on
    close = line.top - prev.bottom <= 0.6 * line.size
    wrapped = (
        not _ENDS_SENTENCE.search(prev.text)
        and not _STARTS_DEFINITION.match(line.text)
        and _reaches_box_edge(prev, line)
    )
    return close and (starts_lower or wrapped)


def _join(texts: list[str]) -> str:
    out = texts[0]
    for text in texts[1:]:
        if re.search(r"[a-z]-$", out) and text[:1].islower():
            out = out[:-1] + text  # "mem-" + "brane." → "membrane."
        else:
            out = f"{out} {text}"
    return out


def to_blocks(lines: list[Line], source: str) -> list[Block]:
    lines = _drop_running_text([_clean(line) for line in lines])
    if not lines:
        return []
    body = _page_body_sizes(lines)
    is_heading = [
        _is_heading(line, body[line.page], lines[i + 1] if i + 1 < len(lines) else None)
        for i, line in enumerate(lines)
    ]
    big_sizes = sorted(
        {
            round(ln.size)
            for ln, h in zip(lines, is_heading, strict=True)
            if h and ln.size > body[ln.page]
        }
    )
    level_of = {size: i + 1 for i, size in enumerate(reversed(big_sizes))}

    blocks: list[Block] = []
    headings: list[tuple[int, str]] = []  # (level, text) of the headings above
    open_block: _Open | None = None
    last_heading: Line | None = None  # set while the previous line was a heading

    def flush() -> None:
        nonlocal open_block
        if open_block:
            path = tuple(h for _, h in headings)
            text = _join(open_block.texts)
            lead = open_block.first.bold_lead
            lead = lead if lead and text.startswith(lead) else ""
            blocks.append(Block(open_block.kind, text, source, path, open_block.page, lead))
        open_block = None

    for line, heading in zip(lines, is_heading, strict=True):
        if heading:
            flush()
            level = level_of.get(round(line.size), len(level_of) + 1)
            # a long large-font heading continued on the next line; stacked short bold lines
            # (author names, run-in headings) and short lines stay separate
            wraps = (
                last_heading is not None
                and line.size > body[line.page]
                and last_heading.page == line.page
                and last_heading.box_right == line.box_right
                and round(last_heading.size) == round(line.size)
                and 0 <= line.top - last_heading.bottom <= 0.6 * line.size
                and _reaches_box_edge(last_heading, line)
            )
            if wraps:
                text = _join([blocks[-1].text, line.text])
                blocks[-1] = replace(blocks[-1], text=text)
                headings[-1] = (level, text)
            else:
                headings = [h for h in headings if h[0] < level]
                path = tuple(h for _, h in headings)
                blocks.append(Block("heading", line.text, source, path, line.page))
                headings.append((level, line.text))
            last_heading = line
            continue
        last_heading = None

        bullet = _BULLET.match(line.text)
        if bullet:
            flush()
            open_block = _Open("bullet", line.page, [bullet["text"]], line, line)
        elif open_block and _continues(open_block, line):
            open_block.texts.append(line.text)
            open_block.last = line
        else:
            flush()
            open_block = _Open("paragraph", line.page, [line.text], line, line)
    flush()
    return blocks
