"""PDF reader: pdfplumber lines with font size and weight, then the structure stage."""

from pathlib import Path
from statistics import median

import pdfplumber
from pdfplumber.utils import extract_text

from autoflashcards.models import Block, Line
from autoflashcards.structure import to_blocks

_BOLD_MARKERS = ("bold", "black", "heavy", "semibold")
COLUMN_GAP = 1.2  # a blank band this many font sizes wide separates columns or boxes
MARKER_CHARS = 2
ROW_GAP = 1.5  # a blank band this many font sizes tall separates stacked regions
# A gap wider than this share of the font size is a word space. pdfplumber's default (a fixed
# 3pt) runs words together in small fonts and splits words in some typeset PDFs
WORD_GAP_RATIO = 0.15
# Letter boxes overlapping by more than this share of the font size, typically, mean the
# PDF's glyph widths are wrong (common in PowerPoint exports), so gaps can't find spaces
OVERLAP_RATIO = 0.1
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

    Gaps are measured between visible characters only. The gap after a bullet marker ("•",
    "1.") can be as wide as a gutter, so a piece of one or two letters is never split off.
    """
    segments: list[list[dict]] = [[]]
    last = None  # previous visible character
    for char in sorted(chars, key=lambda c: c["x0"]):
        if char["text"].strip():
            gutter = last and char["x0"] - last["x1"] > COLUMN_GAP * last["size"]
            if gutter and len(_visible(segments[-1])) > MARKER_CHARS:
                segments.append([])
            last = char
        segments[-1].append(char)
    return [s for s in segments if _visible(s)]


def _widest_gap(spans: list[tuple[float, float]]) -> tuple[float, float]:
    """Widest blank stretch between (start, end) spans along one axis: (width, middle)."""
    spans = sorted(spans)
    best, middle = 0.0, 0.0
    reach = spans[0][1]
    for start, end in spans[1:]:
        if start - reach > best:
            best, middle = start - reach, (start + reach) / 2
        reach = max(reach, end)
    return best, middle


def _in_reading_order(segments: list[list[dict]]) -> list[list[list[dict]]]:
    """A page's line segments grouped into text boxes, boxes in reading order (recursive
    XY-cut).

    Cut the region at its widest blank band, vertical (left part first) or horizontal (top
    part first), and repeat in each part until no band is wide enough; what's left is a box.
    This reads two-column articles column by column, and handout pages with 2x2 slides slide
    by slide, then each slide's boxes in turn.
    """
    if len(segments) < 2:
        return [segments] if segments else []
    visible = [_visible(s) for s in segments]
    size = median(c["size"] for v in visible for c in v)
    x_gap, x_cut = _widest_gap(
        [(min(c["x0"] for c in v), max(c["x1"] for c in v)) for v in visible]
    )
    y_gap, y_cut = _widest_gap(
        [(min(c["top"] for c in v), max(c["bottom"] for c in v)) for v in visible]
    )

    if x_gap >= COLUMN_GAP * size and x_gap >= y_gap:
        first = [
            s for s, v in zip(segments, visible, strict=True) if min(c["x0"] for c in v) < x_cut
        ]
    elif y_gap >= ROW_GAP * size:
        first = [
            s for s, v in zip(segments, visible, strict=True) if min(c["top"] for c in v) < y_cut
        ]
    else:
        return [sorted(segments, key=lambda s: (_top(s), min(c["x0"] for c in _visible(s))))]
    rest = [s for s in segments if not any(s is f for f in first)]
    return _in_reading_order(first) + _in_reading_order(rest)


def _top(chars: list[dict]) -> float:
    return min(c["top"] for c in _visible(chars))


def _text(chars: list[dict]) -> str:
    """Line text. Spaces come from the gaps between letters, unless the letter boxes overlap
    too much to measure gaps; then the PDF's own space characters are used. (Gaps are the
    default because some typeset PDFs put stray space characters inside words.)"""
    chars = [{**c, "text": UNMAPPED} if c["text"].startswith("(cid:") else c for c in chars]
    visible = sorted(_visible(chars), key=lambda c: c["x0"])
    steps = [b["x0"] - a["x1"] for a, b in zip(visible, visible[1:], strict=False)]
    if steps and median(steps) < -OVERLAP_RATIO * visible[0]["size"]:
        return extract_text(chars, keep_blank_chars=True)
    return extract_text(visible, x_tolerance_ratio=WORD_GAP_RATIO)


def _bold_lead(chars: list[dict]) -> str:
    """Text of the bold run that starts a line, allowing a short marker such as "1." first."""
    visible = sorted(_visible(chars), key=lambda c: c["x0"])
    bold = [_is_bold(c["fontname"]) for c in visible]
    start = bold.index(True) if True in bold else None
    if start is None or start > 3:
        return ""
    end = bold.index(False, start) if False in bold[start:] else len(bold)
    return _text(visible[start:end])


def read_lines(path: Path) -> list[Line]:
    lines = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                # dedupe: some PDFs print a glyph twice in the same spot (fake bold, ligatures).
                # pdfplumber joins everything at one height into a line, so split lines at
                # wide gaps first: pieces side by side belong to different columns or boxes
                segments = [
                    segment
                    for r in page.dedupe_chars().extract_text_lines(keep_blank_chars=True)
                    if _visible(r["chars"])
                    for segment in _segments(_unique(r["chars"]))
                ]
                for box in _in_reading_order(segments):
                    box_right = max(c["x1"] for chars in box for c in _visible(chars))
                    for chars in box:
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
                                bold_lead=_bold_lead(chars),
                                x1=max(c["x1"] for c in visible),
                                box_right=box_right,
                            )
                        )
    except Exception as err:  # pdfminer raises many types for damaged or encrypted files
        raise ValueError(f"can't read {path.name}: {err}") from err
    return lines


def read_pdf(path: Path) -> list[Block]:
    return to_blocks(read_lines(path), path.name)
