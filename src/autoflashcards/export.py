"""Anki export. IDs are fixed or derived from content, so re-imports update instead of duplicate.

Cards must be deduplicated first (dedupe.py): Anki allows one note per ID, and the ID comes
from the front.
"""

import csv
import hashlib
import html
import json
import re
import tempfile
from dataclasses import asdict
from pathlib import Path

import genanki

from autoflashcards.models import Block, Card, normalize

# Fixed forever: changing one makes Anki create a second note type on the next import
BASIC_MODEL_ID = 1854201137
CLOZE_MODEL_ID = 1854201138
DIAGRAM_TYPED_MODEL_ID = 1854201139  # was "Image Occlusion (autoflashcards)", with typing
DIAGRAM_MODEL_ID = 1854201140

_CSS = (
    ".card { font-family: sans-serif; font-size: 20px; text-align: center; }\n"
    ".source { margin-top: 1.5em; font-size: 12px; color: #888; }"
)

BASIC_MODEL = genanki.Model(
    BASIC_MODEL_ID,
    "Basic (autoflashcards)",
    fields=[{"name": "Front"}, {"name": "Back"}, {"name": "Source"}],
    templates=[
        {
            "name": "Card 1",
            "qfmt": "{{Front}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Back}}<div class="source">{{Source}}</div>',
        }
    ],
    css=_CSS,
)

CLOZE_MODEL = genanki.Model(
    CLOZE_MODEL_ID,
    "Cloze (autoflashcards)",
    fields=[{"name": "Text"}, {"name": "Back Extra"}, {"name": "Source"}],
    templates=[
        {
            "name": "Cloze",
            "qfmt": "{{cloze:Text}}",
            "afmt": '{{cloze:Text}}<br>{{Back Extra}}<div class="source">{{Source}}</div>',
        }
    ],
    css=_CSS,
    model_type=genanki.Model.CLOZE,
)


class _StockModel(genanki.Model):
    """A note type that Anki treats as one of its own built-in kinds. Anki recognizes Image
    Occlusion by `originalStockKind`, not by name, and only then opens its occlusion editor."""

    def __init__(self, *args, stock_kind: int, **kwargs):
        super().__init__(*args, **kwargs)
        self.stock_kind = stock_kind

    def to_json(self, timestamp: float, deck_id):
        return {**super().to_json(timestamp, deck_id), "originalStockKind": self.stock_kind}


# Anki's built-in Image Occlusion note type (Anki 23.10+), copied from Anki 26.09: same
# fields, templates and CSS, so Anki's occlusion editor can move, resize and delete boxes
_IO_TEMPLATE = """{{#Header}}<div>{{Header}}</div>{{/Header}}
<div style="display: none">{{cloze:Occlusion}}</div>
<div id="err"></div>
<div id="image-occlusion-container">
    {{Image}}
    <canvas id="image-occlusion-canvas"></canvas>
</div>
<script>
try {
    anki.imageOcclusion.setup();
} catch (exc) {
    document.getElementById("err").innerHTML = `Error loading image occlusion. Is your Anki version up to date?<br><br>${exc}`;
}
</script>
"""  # noqa: E501
# Writes each box's number, the N of its cloze in Image Labels, on the image, so the line to fix
# is easy to find: every box's while the Box Numbers button is on, and always the box with no
# label yet (`afgMissing`), which also gets an outline. The hidden cloze divs hold each
# shape's position as a fraction of the image, and Anki's container is position: relative,
# so percentages place the numbers. Text shapes have no box to number. Anki re-renders the
# card when its note is edited, in the same page: the button's state is kept on `window`, so
# the numbers stay on.
_NUMBERS = """<script>
window.afgMissing = null;
window.afgDrawNumbers = () => {
    const container = document.getElementById("image-occlusion-container");
    container.querySelectorAll(".afg-number, .afg-outline").forEach((el) => el.remove());
    for (const shape of document.querySelectorAll("[data-ordinal][data-left]")) {
        const n = shape.dataset.ordinal, missing = n === window.afgMissing;
        if (shape.dataset.shape === "text" || !(window.afgNumbers || missing)) continue;
        const left = `${shape.dataset.left * 100}%`, top = `${shape.dataset.top * 100}%`;
        if (missing && shape.dataset.width) {
            const outline = document.createElement("div");
            outline.className = "afg-outline";
            Object.assign(outline.style, { left, top,
                width: `${shape.dataset.width * 100}%`, height: `${shape.dataset.height * 100}%` });
            container.appendChild(outline);
        }
        const badge = document.createElement("div");
        badge.className = "afg-number";
        badge.textContent = n;
        Object.assign(badge.style, { left, top });
        container.appendChild(badge);
    }
};
window.afgDrawNumbers();
</script>
"""
# Anki's own Toggle Masks button keeps its state inside Anki's script but redraws the masks
# whenever the card is re-rendered, so after an edit the masks are back and the next press
# can do nothing. This button hides the masks itself and keeps its state on `window`, like
# Box Numbers. Shift+M, Anki's shortcut for it, still works. Back only: on the front, hidden
# masks would give the answer away.
_MASKS = """<div><button id="afg-masks" onclick="afgToggle('afgMasksOff')">Toggle Masks</button>
<button id="afg-numbers" onclick="afgToggle('afgNumbers')">Box Numbers</button></div>
<script>
window.afgToggle = (setting) => {
    if (setting) window[setting] = !window[setting];
    document.getElementById("image-occlusion-canvas").style.visibility =
        window.afgMasksOff ? "hidden" : "";
    window.afgDrawNumbers();
};
if (!window.afgShortcut) {
    window.afgShortcut = true;
    window.addEventListener("keydown", (event) => {
        if (event.key === "M" && document.getElementById("afg-masks")) afgToggle("afgMasksOff");
    });
}
afgToggle();
</script>
"""
# The typing box. For a box added in Anki's editor, Image Labels has no cloze with its number, and
# Anki shows "run Tools > Empty Cards" there instead; the script replaces that with the box's
# number and what to add. A template can't contain two braces in a row, so they're built in JS.
_TYPE_ANSWER = """<div id="afg-type">{{type:cloze:Image Labels}}</div>
{{#Image Labels}}<script>
(() => {
    const type = document.getElementById("afg-type");
    // the box was deleted (the back marks it cloze-highlight), so there's nothing to type
    if (!document.querySelector(".cloze[data-ordinal], .cloze-highlight[data-ordinal]")) {
        type.hidden = true;  // _NO_BOX says what to do
        return;
    }
    // Only Anki's warning, not its typing box, means this box has no answer. Previews drop
    // the typing box altogether, and so does the back, so an empty div says nothing.
    if (type.querySelector("#typeans") || !type.textContent.trim()) return;
    const box = document.querySelector(".cloze[data-ordinal]");
    if (!box) return;  // the back
    const n = box.dataset.ordinal;
    const open = "{" + "{", close = "}" + "}";
    type.textContent = `Box ${n} has no answer yet. To type it, add ${open}c${n}::label${close}`
        + " to this note's Image Labels field.";
    window.afgMissing = n;
    window.afgDrawNumbers();
})();
</script>{{/Image Labels}}
"""

# Anki's editor warns about cloze deletions in a field that the front doesn't show with a
# cloze filter (`cloze-only:` on the back doesn't count). This one renders only when Image Labels
# is empty, so it never shows anything.
_CLOZE_ANSWERS = "{{^Image Labels}}{{cloze:Image Labels}}{{/Image Labels}}\n"

# A box deleted in Anki's editor leaves its card behind, showing the figure with no boxes.
# Anki's Tools > Empty Cards deletes that card, once Image Labels has no line for it either.
# When there's no line, Anki adds its own "No cloze N found" notice under the card; this
# says the same in one message instead. The notice is found by its link, which, unlike its
# text, is the same in every language. Anki runs the scripts after the whole card is in.
# On the back, the card's box is marked cloze-highlight instead of cloze.
_NO_BOX = """<div id="afg-no-box"></div>
<script>
if (!document.querySelector(".cloze[data-ordinal], .cloze-highlight[data-ordinal]")) {
    const notice = document.querySelector('a[href*="#no-cloze"]');
    if (notice) notice.parentElement.hidden = true;
    document.getElementById("afg-no-box").textContent = "This card's box was deleted. "
        + "To remove the card, "
        + (notice ? "" : "delete the box's line in Image Labels, then ")
        + "run Tools > Empty Cards.";
}
</script>
"""


def _diagram_model(model_id: int, name: str, typed: bool) -> _StockModel:
    """Anki's Image Occlusion note type plus two fields: Image Labels, the labels as cloze
    deletions numbered like the boxes ({{c2::Nucleolus}}), and Source, shown under the card
    like on the text cards. The back shows the label of the box this card hides (so text to
    speech has it to read), or with `typed`, `{{type:cloze:Image Labels}}` asks for it."""
    answer = _TYPE_ANSWER if typed else '<div class="label">{{cloze-only:Image Labels}}</div>\n'
    return _StockModel(
        model_id,
        name,
        # `tag` is the field's role, which Anki uses to find the image and the boxes
        fields=[
            {"name": "Occlusion", "tag": 0, "preventDeletion": True},
            {"name": "Image", "tag": 1, "preventDeletion": True},
            {"name": "Header", "tag": 2, "preventDeletion": True},
            {"name": "Back Extra", "tag": 3, "preventDeletion": True},
            {"name": "Comments", "tag": 4, "preventDeletion": False},
            {"name": "Image Labels"},
            {"name": "Source"},
        ],
        templates=[
            {
                "name": "Image Occlusion",
                "qfmt": _IO_TEMPLATE
                + _NUMBERS
                + _NO_BOX
                + (_TYPE_ANSWER if typed else _CLOZE_ANSWERS),
                "afmt": _IO_TEMPLATE
                + _NUMBERS
                + _NO_BOX
                + answer
                + _MASKS
                + """{{#Back Extra}}<div>{{Back Extra}}</div>{{/Back Extra}}
<div class="source">{{Source}}</div>
""",
            }
        ],
        css="""#image-occlusion-canvas {
    --inactive-shape-color: #ffeba2;
    --active-shape-color: #ff8e8e;
    --inactive-shape-border: 1px #212121;
    --active-shape-border: 1px #212121;
    --highlight-shape-color: #ff8e8e00;
    --highlight-shape-border: 1px #ff8e8e;
}

.card {
    font-family: arial;
    font-size: 20px;
    text-align: center;
    color: black;
    background-color: white;
}

.source { margin-top: 1.5em; font-size: 12px; color: #888; }

.afg-number {
    position: absolute;
    transform: translate(-50%, -50%);
    min-width: 1.4em;
    border-radius: 0.7em;
    background: #212121;
    color: white;
    font: bold 13px/1.4em arial;
    pointer-events: none;
}

.afg-outline { position: absolute; outline: 3px solid #d00; pointer-events: none; }
""",
        model_type=genanki.Model.CLOZE,
        stock_kind=6,  # IMAGE_OCCLUSION in Anki's StockNotetype.Kind
    )


DIAGRAM_MODEL = _diagram_model(DIAGRAM_MODEL_ID, "Image Occlusion (autoflashcards)", typed=False)
DIAGRAM_TYPED_MODEL = _diagram_model(
    DIAGRAM_TYPED_MODEL_ID, "Image Occlusion (autoflashcards, type in the answer)", typed=True
)


def _stable_id(text: str) -> int:
    """Positive 31-bit integer from text, for Anki deck IDs."""
    return int(hashlib.sha256(text.encode()).hexdigest(), 16) % (1 << 31)


def _tag(text: str) -> str:
    """Anki tags can't contain spaces; keep letters, digits, - and _."""
    return re.sub(r"[^\w-]+", "_", text.lower()).strip("_")


def _html(text: str) -> str:
    """Anki fields are HTML: escape the text, and show line breaks (one per bullet)."""
    return html.escape(text).replace("\n", "<br>")


def tags(card: Card) -> list[str]:
    result = [f"afg::rule::{card.rule}"]
    heading_tag = "::".join(t for t in map(_tag, card.heading_path) if t)
    if heading_tag:
        result.append(heading_tag)
    return result


def note_guid(deck_name: str, card: Card) -> str:
    # The front identifies a card; a fixed typo in the back updates the same note
    return genanki.guid_for(deck_name, normalize(card.front))


def to_note(deck_name: str, card: Card) -> genanki.Note:
    if card.kind == "diagram":
        (image,) = card.media
        return genanki.Note(
            model=DIAGRAM_TYPED_MODEL if card.typed else DIAGRAM_MODEL,
            fields=[
                card.occlusion,
                f'<img src="{html.escape(image)}">',
                "",
                "",
                "",
                card.answers,
                _html(card.source_label),
            ],
            tags=tags(card),
            guid=note_guid(deck_name, card),
        )
    model = CLOZE_MODEL if card.kind == "cloze" else BASIC_MODEL
    return genanki.Note(
        model=model,
        fields=[_html(card.front), _html(card.back), _html(card.source_label)],
        tags=tags(card),
        guid=note_guid(deck_name, card),
    )


def write_apkg(
    cards: list[Card], deck_name: str, out: Path, media: dict[str, bytes] | None = None
) -> None:
    """`media` maps image file names used by diagram cards to their JPEG bytes. Only images
    of the cards given are packed, so dropped cards leave nothing behind."""
    deck = genanki.Deck(_stable_id(deck_name), deck_name)
    for card in cards:
        deck.add_note(to_note(deck_name, card))
    used = {name for card in cards for name in card.media}
    with tempfile.TemporaryDirectory() as folder:  # genanki packs media from files
        paths = []
        for name, data in (media or {}).items():
            if name not in used:
                continue
            (Path(folder) / name).write_bytes(data)
            paths.append(str(Path(folder) / name))
        genanki.Package(deck, media_files=paths).write_to_file(str(out))


# Anki 2.1.55+ reads these headers, so the import needs no manual column mapping.
# Commas, not tabs, because Excel splits a double-clicked .csv on commas; the readable
# columns come first and the #columns line doubles as Excel's header row.
_CSV_HEADER = """#separator:comma
#html:true
#columns:Front,Back,Tags,Note type,Deck,ID
#tags column:3
#notetype column:4
#deck column:5
#guid column:6
"""


def write_csv(cards: list[Card], deck_name: str, out: Path) -> None:
    """CSV for Anki's built-in Basic and Cloze note types (which have no Source field, so
    the source line goes at the end of the second field). Written with a BOM: without one,
    Excel and Notepad read the UTF-8 as Windows-1252 ("·" shows as "Â·"). Diagram cards
    are left out: their images can only travel in the .apkg."""
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        f.write(_CSV_HEADER)
        writer = csv.writer(f, lineterminator="\n")
        for card in (c for c in cards if c.kind != "diagram"):
            source = f"<br><small>{_html(card.source_label)}</small>"
            notetype = "Cloze" if card.kind == "cloze" else "Basic"
            writer.writerow([
                _html(card.front),
                _html(card.back) + source,
                " ".join(tags(card)),
                notetype,
                deck_name,
                note_guid(deck_name, card),
            ])  # fmt: skip


# The note type the Simple Image Occlusion add-on (AnkiWeb 675107747) creates. Its templates
# aren't ours to ship, so these notes go into the user's copy of it, through a CSV import
SIO_NOTETYPE = "Image Occlusion Simple (v2)"


def write_sio_csv(
    cards: list[Card], deck_name: str, out: Path, pdfs: dict[str, Path] | None = None
) -> None:
    """Diagram cards as notes of the Simple Image Occlusion add-on: one note per diagram,
    whose boxes and their labels are edited in the add-on's editor. `Words` lists the labels
    the way the add-on's editor saves them, sorted and joined with "; ".

    `pdfs` maps source file names to their paths, to fill the add-on's
    `HeaderURL_filepdf#page=` field, which makes the header a link to the figure's page.
    Without it the column is left out, so a re-import keeps links added in Anki."""
    columns = ["Front", "Header", "Words", "Tags", "ID"]
    if pdfs is not None:
        columns.insert(2, "HeaderURL_filepdf#page=")
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        f.write(
            f"#separator:comma\n#html:true\n#notetype:{SIO_NOTETYPE}\n#deck:{deck_name}\n"
            f"#columns:{','.join(columns)}\n#tags column:{columns.index('Tags') + 1}\n"
            f"#guid column:{columns.index('ID') + 1}\n"
        )
        writer = csv.writer(f, lineterminator="\n")
        for card in (c for c in cards if c.kind == "diagram"):
            row = [
                card.sio,
                _html(card.source_label),
                html.escape("; ".join(sorted(card.back.splitlines())), quote=False),
                " ".join(tags(card)),
                # not the .apkg note's ID: Anki won't turn a note into another note type
                genanki.guid_for(deck_name, normalize(card.front), "sio"),
            ]
            if pdfs is not None:
                pdf = pdfs.get(card.source)
                link = f"{pdf.resolve().as_uri()}#page={card.page}" if pdf and card.page else ""
                row.insert(2, html.escape(link))
            writer.writerow(row)


def write_media(cards: list[Card], media: dict[str, bytes], folder: Path) -> int:
    """Write the images the cards use into `folder`; returns how many."""
    folder.mkdir(parents=True, exist_ok=True)
    used = {name for card in cards for name in card.media}
    for name in used:
        (folder / name).write_bytes(media[name])
    return len(used)


def write_json(
    blocks: list[Block], cards: list[Card], removed: list[tuple[Card, str]], out: Path
) -> None:
    """Every stage's output, for checking what was extracted and why cards were dropped."""

    def card_dict(card: Card) -> dict:
        return {**asdict(card), "source_label": card.source_label}

    data = {
        "blocks": [asdict(b) for b in blocks],
        "cards": [card_dict(c) for c in cards],
        "removed": [{**card_dict(c), "reason": reason} for c, reason in removed],
    }
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def preview_text(cards: list[Card]) -> str:
    """The cards as plain text, numbered, for checking them before writing a deck."""
    entries = []
    for n, card in enumerate(cards, 1):
        lines = [f"{n}. {card.front}"]
        lines += [f"   {line}" for line in card.back.splitlines()]
        lines.append(f"   ({card.rule}; {card.source_label})")
        entries.append("\n".join(lines))
    return "\n\n".join(entries) + "\n"
