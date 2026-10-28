"""Diagram cards: find labeled figures and turn them into Anki Image Occlusion notes.

A figure is a picture in the PDF (joined from its tiles when the PDF cuts it into strips)
or a cluster of drawn shapes. Its image is drawn without the slide background: only the
pictures and shapes inside the figure's frame are kept, and all text. Its labels are short text
lines on or next to it, from the PDF's text layer or, when the labels are part of a picture,
read with Tesseract. Each figure becomes one note of Anki's built-in Image Occlusion type:
the image, and a box over each label that Anki shows as a mask and that can be moved,
resized or deleted in Anki's occlusion editor.
"""

import csv
import hashlib
import html
import io
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from statistics import median

import pdfplumber
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw
from PIL import Image

from autoflashcards.models import Card
from autoflashcards.readers.pdf import _segments, _text, _unique, _visible

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")
RESOLUTION = 150  # dpi of the card images
OCR_RESOLUTION = 300  # Tesseract reads small labels better at 300 dpi
OCR_CONFIDENCE = 70  # Tesseract word confidence (0-100) below which a word is noise
MIN_FIGURE = 72  # points; smaller pictures are bullet markers or logos
MAX_PAGE_SHARE = 0.8  # pictures or shapes covering more of the page are backgrounds
CLUSTER_GAP = 6  # points; drawn shapes this close belong to the same figure
TILE_GAP = 1  # points; tiles of one picture touch within this, and their edges line up
MIN_SHAPES = 3  # a lone frame or rule isn't a figure
MARGIN = 36  # points around a figure where its labels may sit
MIN_LABELS, MAX_LABELS = 2, 30
MAX_LABEL_WORDS, MAX_LABEL_CHARS = 5, 40
MAX_LABEL_SIZE = 1.3  # text larger than this many times the median is a title
STACK_GAP = 0.6  # lines closer than this many line heights are one label ("Nuclear / envelope")
PAD = 3  # pixels added around a label's box
JPEG_QUALITY = 85
_CAPTION = re.compile(r"(fig(ure)?|table|source|image)\b|\([a-z]\)", re.IGNORECASE)
# a line ending in one of these words was wrapped mid-sentence: body text, not a label
_WRAPPED = re.compile(
    r"\b(a|an|the|of|in|and|or|to|for|with|by|from|that|on|at|as|is|are)$", re.IGNORECASE
)
_MEASURE = re.compile(r"\d[\d.,]*\s*[nµμup]?m")  # scale bars: "0.5 µm", "25 nm"

Box = tuple[float, float, float, float]  # x0, top, x1, bottom


@dataclass(frozen=True)
class Label:
    text: str
    box: Box  # in image pixels


@dataclass
class Diagram:
    image: Image.Image
    labels: list[Label]  # top to bottom, then left to right
    source: str
    page: int | None = None
    number: int = 1  # figure number on its page


def _is_label(text: str) -> bool:
    text = text.strip()
    return (
        0 < len(text) <= MAX_LABEL_CHARS
        and len(text.split()) <= MAX_LABEL_WORDS
        and any(sum(c.isalpha() for c in word) >= 3 for word in text.split())
        and not text.endswith((".", ":", ";", ","))
        and not text.startswith(("•", "-", "–"))
        and not any(mark in text for mark in ("@", "www.", "http", "\ufffd"))
        and not _CAPTION.match(text)
        and not _WRAPPED.search(text)
        and not _MEASURE.fullmatch(text)
    )


def _overlaps(a: Box, b: Box, gap: float = 0) -> bool:
    return a[0] - gap < b[2] and b[0] - gap < a[2] and a[1] - gap < b[3] and b[1] - gap < a[3]


def _contains(outer: Box, inner: Box) -> bool:
    return (
        outer[0] - TILE_GAP <= inner[0]
        and outer[1] - TILE_GAP <= inner[1]
        and inner[2] <= outer[2] + TILE_GAP
        and inner[3] <= outer[3] + TILE_GAP
    )


def _union(boxes: list[Box]) -> Box:
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _area(box: Box) -> float:
    return (box[2] - box[0]) * (box[3] - box[1])


def _bbox(obj: dict) -> Box:
    return (obj["x0"], obj["top"], obj["x1"], obj["bottom"])


def _tiles(boxes: list[Box]) -> list[Box]:
    """Join pictures that are tiles of one picture: some PDFs cut a figure into strips or a
    grid. Two tiles touch and share both side edges (a column) or top and bottom (a row).
    The joined pictures keep the order their first tiles are drawn in."""

    def joined(a: Box, b: Box) -> bool:
        column = abs(a[0] - b[0]) <= TILE_GAP and abs(a[2] - b[2]) <= TILE_GAP
        row = abs(a[1] - b[1]) <= TILE_GAP and abs(a[3] - b[3]) <= TILE_GAP
        return (column or row) and _overlaps(a, b, TILE_GAP)

    group = list(range(len(boxes)))

    def find(i: int) -> int:
        while group[i] != i:
            i = group[i]
        return i

    for i, j in combinations(range(len(boxes)), 2):
        if joined(boxes[i], boxes[j]):
            group[find(i)] = find(j)
    members: dict[int, list[Box]] = {}
    for i, box in enumerate(boxes):
        members.setdefault(find(i), []).append(box)
    return [_union(tiles) for tiles in members.values()]


def _clusters(boxes: list[Box], gap: float) -> list[tuple[Box, int]]:
    """Group boxes that touch (within `gap`): (bounding box, number of boxes)."""
    groups: list[list[Box]] = []
    for box in boxes:
        touching = [g for g in groups if any(_overlaps(box, b, gap) for b in g)]
        merged = [box] + [b for g in touching for b in g]
        groups = [g for g in groups if not any(g is t for t in touching)] + [merged]
    return [(_union(g), len(g)) for g in groups]


def _figures(page) -> list[tuple[Box, bool]]:
    """Figure regions on a page, top to bottom: (box, is_picture)."""
    page_area = page.width * page.height

    def figure_sized(b: Box) -> bool:
        w, h = b[2] - b[0], b[3] - b[1]
        return w >= MIN_FIGURE and h >= MIN_FIGURE and w * h <= MAX_PAGE_SHARE * page_area

    pictures = [b for b in _tiles([_bbox(image) for image in page.images]) if figure_sized(b)]

    def background(p: Box, q: Box) -> bool:
        """p is under q, which is drawn later: q lies inside p, or covers p mostly and is
        about as large."""
        overlap = max(min(p[2], q[2]) - max(p[0], q[0]), 0) * max(
            min(p[3], q[3]) - max(p[1], q[1]), 0
        )
        return _contains(p, q) or (overlap >= _area(q) / 2 and _area(q) >= _area(p) / 2)

    # a picture with another figure-sized picture on it is a background (a slide, a texture)
    pictures = [
        p for i, p in enumerate(pictures) if not any(background(p, q) for q in pictures[i + 1 :])
    ]
    tables = [t.bbox for t in page.find_tables()]
    shapes = [
        b
        for b in map(_bbox, page.rects + page.lines + page.curves)
        if (b[2] - b[0]) * (b[3] - b[1]) <= MAX_PAGE_SHARE * page_area
    ]
    drawings = [
        box
        for box, count in _clusters(shapes, CLUSTER_GAP)
        if count >= MIN_SHAPES
        and figure_sized(box)
        and not any(_overlaps(box, t) for t in tables)
        and not any(_overlaps(box, p) for p in pictures)
    ]
    figures = [(b, True) for b in pictures] + [(b, False) for b in drawings]
    return sorted(figures, key=lambda f: (f[0][1], f[0][0]))


def _text_lines(page) -> list[tuple[str, Box]]:
    """A page's text lines split at column gaps, titles left out: (text, box in points)."""
    found = []
    for row in page.dedupe_chars().extract_text_lines(keep_blank_chars=True):
        for chars in _segments(_unique(row["chars"])):
            visible = _visible(chars)
            box = (
                min(c["x0"] for c in visible),
                min(c["top"] for c in visible),
                max(c["x1"] for c in visible),
                max(c["bottom"] for c in visible),
            )
            found.append((_text(chars).strip(), box, median(c["size"] for c in visible)))
    if not found:
        return []
    typical = median(size for _, _, size in found)
    return [(text, box) for text, box, size in found if size <= MAX_LABEL_SIZE * typical]


def _stacked(lines: list[tuple[str, Box]]) -> list[tuple[str, Box]]:
    """Join the lines of a label set on two or more lines ("Nuclear" over "envelope"): the
    lower line starts within STACK_GAP line heights and is aligned left or centered."""
    labels: list[tuple[str, Box]] = []
    for text, box in sorted(lines, key=lambda line: line[1][1]):
        height = box[3] - box[1]
        for n, (above, upper) in enumerate(labels):
            upper_height = upper[3] - upper[1]
            line_height = upper_height / (above.count("\n") + 1)
            aligned = (
                abs(box[0] - upper[0]) < line_height
                or abs((box[0] + box[2]) - (upper[0] + upper[2])) < 2 * line_height
            )
            close = -0.3 * height < box[1] - upper[3] < STACK_GAP * line_height
            if aligned and close and 0.75 < height / line_height < 1.33:
                joined = f"{above}\n{text}"
                labels[n] = (joined, _union([upper, box]))
                break
        else:
            labels.append((text, box))
    # newlines only counted lines above; a label reads as one phrase
    return [(re.sub(r"-\n", "-", text).replace("\n", " "), box) for text, box in labels]


def _text_labels(lines: list[tuple[str, Box]], figure: Box) -> list[tuple[str, Box]] | None:
    """Labels for a figure from the text layer: short text on it or within MARGIN of it.
    Lines are joined first, so a paragraph or bullet next to a figure isn't taken for
    labels. None when other text (a sentence, a wrapped line) sits on the figure: then it's
    a text box or a slide background, not a diagram."""
    if any(_overlaps(box, figure) and not _is_label(text) for text, box in lines):
        return None
    near = _stacked([(t, b) for t, b in lines if _overlaps(b, figure, MARGIN)])
    return [(text, box) for text, box in near if _is_label(text)]


def _tesseract() -> str | None:
    found = shutil.which("tesseract")
    windows = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")
    return found or (str(windows) if windows.exists() else None)


def ocr_labels(image: Image.Image) -> list[Label]:
    """Labels printed in a picture, read by Tesseract in sparse-text mode (--psm 11)."""
    exe = _tesseract()
    if exe is None:
        raise ValueError("reading labels in pictures needs Tesseract (see the README)")
    png = io.BytesIO()
    image.convert("RGB").save(png, "PNG")
    try:
        tsv = subprocess.run(
            [exe, "stdin", "stdout", "--psm", "11", "tsv"],
            input=png.getvalue(),
            capture_output=True,
            check=True,
            timeout=120,
        ).stdout.decode("utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError) as err:
        raise ValueError(f"Tesseract failed: {err}") from err

    rows: dict[tuple[str, ...], list[dict]] = {}
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        if row["level"] == "5" and float(row["conf"]) >= OCR_CONFIDENCE and row["text"].strip():
            key = (row["block_num"], row["par_num"], row["line_num"])
            rows.setdefault(key, []).append(row)

    lines = []
    for words in rows.values():
        # one Tesseract line can hold labels far apart; split where the gap is wide
        words.sort(key=lambda w: int(w["left"]))
        groups = [[words[0]]]
        for prev, word in zip(words, words[1:], strict=False):
            gap = int(word["left"]) - int(prev["left"]) - int(prev["width"])
            if gap > 1.5 * int(prev["height"]):
                groups.append([])
            groups[-1].append(word)
        for group in groups:
            text = " ".join(w["text"] for w in group)
            box = _union(
                [
                    (
                        int(w["left"]),
                        int(w["top"]),
                        int(w["left"]) + int(w["width"]),
                        int(w["top"]) + int(w["height"]),
                    )
                    for w in group
                ]
            )
            if _is_label(text):
                lines.append((text, box))
    return [Label(text, box) for text, box in _stacked(lines)]


def _in_order(labels: list[Label]) -> list[Label]:
    """Top to bottom, then left to right, so box numbers follow the figure as it's read. A
    label whose middle is level with a row's first label is in that row."""
    rows: list[list[Label]] = []
    for label in sorted(labels, key=lambda label: label.box[1]):
        if rows and (label.box[1] + label.box[3]) / 2 < rows[-1][0].box[3]:
            rows[-1].append(label)
        else:
            rows.append([label])
    return [label for row in rows for label in sorted(row, key=lambda label: label.box[0])]


def _render(document: pdfium.PdfDocument, page_number: int, crop: Box, resolution: int):
    """The page region `crop`, drawn with only the pictures and shapes that lie inside it, so
    slide backgrounds, sticky notes and pins around a figure are left out; text is kept."""
    page = document[page_number - 1]  # a fresh copy: removing objects doesn't touch the file
    width, height = page.get_width(), page.get_height()
    for obj in list(page.get_objects(max_depth=0)):
        if obj.type in (pdfium_raw.FPDF_PAGEOBJ_IMAGE, pdfium_raw.FPDF_PAGEOBJ_PATH):
            left, bottom, right, top = obj.get_bounds()  # PDF space: y grows upward
            if not _contains(crop, (left, height - top, right, height - bottom)):
                page.remove_obj(obj)
    x0, top, x1, bottom = crop
    bitmap = page.render(
        scale=resolution / 72,
        crop=(x0, height - bottom, width - x1, top),  # amounts cut from each edge
        fill_color=(255, 255, 255, 255),
    )
    return bitmap.to_pil().convert("RGB")


def _from_text_layer(
    document: pdfium.PdfDocument, page, figure: Box, found: list[tuple[str, Box]]
) -> Diagram:
    crop = _union([figure] + [b for _, b in found])
    crop = (
        max(crop[0] - PAD, 0),
        max(crop[1] - PAD, 0),
        min(crop[2] + PAD, page.width),
        min(crop[3] + PAD, page.height),
    )
    scale = RESOLUTION / 72
    labels = [
        Label(text, tuple((v - crop[i % 2]) * scale for i, v in enumerate(box)))
        for text, box in found
    ]
    image = _render(document, page.page_number, crop, RESOLUTION)
    return Diagram(image, _in_order(labels), "", page.page_number)


def _from_picture(document: pdfium.PdfDocument, page, figure: Box) -> Diagram:
    ratio = RESOLUTION / OCR_RESOLUTION
    labels = [
        Label(label.text, tuple(v * ratio for v in label.box))
        for label in ocr_labels(_render(document, page.page_number, figure, OCR_RESOLUTION))
    ]
    image = _render(document, page.page_number, figure, RESOLUTION)
    return Diagram(image, _in_order(labels), "", page.page_number)


def read_pdf(
    path: Path,
    warn: Callable[[str], None],
    progress: Callable[[int, int], None] | None = None,
) -> list[Diagram]:
    """Labeled figures in a PDF. Pictures with no text on them are read with Tesseract when
    it is installed; `warn` is called once if it isn't. `progress(done, total)` is called
    after each page."""
    diagrams = []
    ocr, warned = _tesseract() is not None, False
    try:
        pdf = pdfplumber.open(path)
    except Exception as err:  # pdfminer raises many types for damaged or encrypted files
        raise ValueError(f"can't read {path.name}: {err}") from err
    with pdf:
        document = pdfium.PdfDocument(path)
        for page in pdf.pages:
            figures = _figures(page)
            lines = _text_lines(page) if figures else []
            number = 0
            for figure, is_picture in figures:
                found = _text_labels(lines, figure)
                if found is not None and len(found) >= MIN_LABELS:
                    diagram = _from_text_layer(document, page, figure, found)
                elif is_picture and not any(_overlaps(b, figure) for _, b in lines):
                    if not ocr:
                        if not warned:
                            warn(
                                f"Note: {path.name} has pictures that may have labels; "
                                "install Tesseract to read them (see the README)."
                            )
                            warned = True
                        continue
                    diagram = _from_picture(document, page, figure)
                else:
                    continue
                if MIN_LABELS <= len(diagram.labels) <= MAX_LABELS:
                    number += 1
                    diagram.source, diagram.number = path.name, number
                    diagrams.append(diagram)
            if progress:
                progress(page.page_number, len(pdf.pages))
    return diagrams


def read_image(path: Path) -> list[Diagram]:
    """A picture file is one diagram; its labels are read with Tesseract."""
    try:
        image = Image.open(path).convert("RGB")
    except OSError as err:
        raise ValueError(f"can't read {path.name}: {err}") from err
    labels = ocr_labels(image)
    if not MIN_LABELS <= len(labels) <= MAX_LABELS:
        return []
    return [Diagram(image, _in_order(labels), path.name)]


def _jpeg(image: Image.Image, media: dict[str, bytes]) -> str:
    """Add the image to `media` under a content-derived name (Anki keeps one media folder
    for all decks, so names must not collide) and return the name. JPEG, because textbook
    figures are often photos."""
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=JPEG_QUALITY)
    data = buffer.getvalue()
    name = f"afg-{hashlib.sha256(data).hexdigest()[:16]}.jpg"
    media[name] = data
    return name


def _boxes(diagram: Diagram) -> list[tuple[float, float, float, float]]:
    """Each label's box, padded, as fractions of the image: (left, top, width, height)."""
    width, height = diagram.image.size
    result = []
    for label in diagram.labels:
        x0, top, x1, bottom = label.box
        x0, top = max(x0 - PAD, 0), max(top - PAD, 0)
        x1, bottom = min(x1 + PAD, width), min(bottom + PAD, height)
        result.append((x0 / width, top / height, (x1 - x0) / width, (bottom - top) / height))
    return result


def _occlusions(diagram: Diagram) -> str:
    """The boxes in Anki's Image Occlusion markup: one rectangle per label. Each box gets
    its own cloze number (c1, c2, ...), which makes it its own card and lets Anki's editor
    move and resize it on its own; `oi=1` keeps the other boxes covered while one is
    asked."""
    shapes = []
    for i, (left, top, width, height) in enumerate(_boxes(diagram)):
        shapes.append(
            f"{{{{c{i + 1}::image-occlusion:rect:left={left:.4f}:top={top:.4f}"
            f":width={width:.4f}:height={height:.4f}:oi=1}}}}"
        )
    return "<br>".join(shapes)


def _sio_front(diagram: Diagram, image: str) -> str:
    """The image and boxes as the Simple Image Occlusion add-on writes them: a div per box,
    positioned in percent, carrying its label in `word`, which the add-on's editor edits
    and its cards ask you to type. The add-on stores " in a word as '."""
    rects = []
    for label, (left, top, width, height) in zip(diagram.labels, _boxes(diagram), strict=True):
        word = html.escape(label.text, quote=False).replace('"', "'")
        rects.append(
            f'<div class="sio-rect" style="left: {left:.4%}; top: {top:.4%}; '
            f'width: {width:.4%}; height: {height:.4%};" word="{word}" hint=""></div>'
        )
    return f'<img class="sio-image" src="{html.escape(image)}">' + "".join(rects)


def _answers(diagram: Diagram) -> str:
    """The labels as cloze deletions numbered like their boxes: the card for box 2 shows the
    text of {{c2::...}} on its back, or asks for it with `{{type:cloze:Image Labels}}`. One per
    line, so a misread label is easy to find and fix in Anki's editor."""
    return "<br>".join(
        f"{{{{c{i + 1}::{html.escape(label.text)}}}}}" for i, label in enumerate(diagram.labels)
    )


def cards(diagrams: list[Diagram], typed: bool = False) -> tuple[list[Card], dict[str, bytes]]:
    """One Image Occlusion note per diagram, and the images (file name -> JPEG bytes). The
    note makes one card per label, and its boxes are edited in one place, in Anki's own
    occlusion editor. `typed` asks to type each card's label."""
    result: list[Card] = []
    media: dict[str, bytes] = {}
    for diagram in diagrams:
        where = diagram.source + (f" p.{diagram.page}" if diagram.page else "")
        image = _jpeg(diagram.image, media)
        result.append(
            Card(
                f"{where} figure {diagram.number}",
                "\n".join(label.text for label in diagram.labels),
                "diagram",
                diagram.source,
                page=diagram.page,
                kind="diagram",
                media=(image,),
                occlusion=_occlusions(diagram),
                answers=_answers(diagram),
                typed=typed,
                sio=_sio_front(diagram, image),
            )
        )
    return result, media
