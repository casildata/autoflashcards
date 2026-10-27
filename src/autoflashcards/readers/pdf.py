"""PDF reader: pdfplumber lines with font size and weight, then the structure stage."""

from pathlib import Path
from statistics import median

import pdfplumber
from pdfplumber.utils import extract_text

from autoflashcards.models import Block, Line
from autoflashcards.structure import to_blocks

_BOLD_MARKERS = ("bold", "black", "heavy", "semibold")
COLUMN_GAP = 2.0  # a gap wider than this many font sizes inside a line is a column gutter
MIN_SPLIT_SHARE = 0.25  # share of a page's lines that must split for it to count as two columns
# A gap wider than this share of the font size is a word space. pdfplumber's default (a fixed
# 3pt) runs words together in small fonts and splits words in some typeset PDFs
WORD_GAP_RATIO = 0.15
UNMAPPED = "�"  # stands in for glyphs the PDF doesn't map to text, shown as "(cid:N)"


def _is_bold(fontname: str) -> bool:
    # embedded fonts look like "ABCDEF+Arial-BoldMT"
    return any(marker in fontname.lower() for marker in _BOLD_MARKERS)


def _visible(chars: list[dict]) -> list[dict]:
    return [c for c in chars if c["text"].strip()]


def _unique(chars: list[dict]) -> list[dict]:
    # extract_text_lines lists a multi-letter char such as "(cid:127)" once per letter
    return list({id(c): c for c in chars}.values())


def _segments(chars: list[dict]) -> list[list[dict]]:
    """Split one line's characters wherever the gap is wide enough to be a column gutter.

    Gaps are measured between visible characters only.
    """
    segments: list[list[dict]] = [[]]
    last = None  # previous visible character
    for char in sorted(chars, key=lambda c: c["x0"]):
        if char["text"].strip():
            if last and char["x0"] - last["x1"] > COLUMN_GAP * last["size"]:
                segments.append([])
            last = char
        segments[-1].append(char)
    return [s for s in segments if _visible(s)]


def _in_reading_order(lines: list[list[dict]], page_width: float) -> list[list[dict]]:
    """Character groups for one page, in reading order: two-column pages left column first.

    pdfplumber joins characters at the same height into one line, so on a two-column page
    each line holds text from both columns. Split those lines at the gutter, then read the
    left column top to bottom, then the right.
    """
    split = [_segments(chars) for chars in lines]
    gutters = [
        (_visible(s[0])[-1]["x1"] + _visible(s[1])[0]["x0"]) / 2 for s in split if len(s) > 1
    ]
    if not gutters or len(gutters) < MIN_SPLIT_SHARE * len(lines):
        return lines
    gutter = median(gutters)
    near = [g for g in gutters if abs(g - gutter) < 0.05 * page_width]
    if len(near) < 0.6 * len(gutters):  # gaps at scattered positions: a table, not columns
        return lines

    left, right = [], []
    for segments in split:
        for segment in segments:
            starts_right = min(c["x0"] for c in _visible(segment)) >= gutter
            (right if starts_right else left).append(segment)
    return sorted(left, key=_top) + sorted(right, key=_top)


def _top(chars: list[dict]) -> float:
    return min(c["top"] for c in _visible(chars))


def _text(chars: list[dict]) -> str:
    chars = [{**c, "text": UNMAPPED} if c["text"].startswith("(cid:") else c for c in chars]
    return extract_text(chars, x_tolerance_ratio=WORD_GAP_RATIO)


def read_lines(path: Path) -> list[Line]:
    lines = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                # dedupe: some PDFs print a glyph twice in the same spot (fake bold, ligatures)
                raw_lines = [
                    _unique(r["chars"])
                    for r in page.dedupe_chars().extract_text_lines()
                    if _visible(r["chars"])
                ]
                for chars in _in_reading_order(raw_lines, page.width):
                    visible = _visible(chars)
                    lines.append(
                        Line(
                            text=_text(chars),
                            page=page.page_number,
                            size=median(c["size"] for c in visible),
                            bold=all(_is_bold(c["fontname"]) for c in visible),
                            x0=min(c["x0"] for c in visible),
                            top=_top(chars),
                            bottom=max(c["bottom"] for c in visible),
                        )
                    )
    except Exception as err:  # pdfminer raises many types for damaged or encrypted files
        raise ValueError(f"can't read {path.name}: {err}") from err
    return lines


def read_pdf(path: Path) -> list[Block]:
    return to_blocks(read_lines(path), path.name)
