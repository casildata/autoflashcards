"""Anki export. IDs are fixed or derived from content, so re-imports update instead of duplicate.

Cards must be deduplicated first (dedupe.py): Anki allows one note per ID, and the ID comes
from the front.
"""

import csv
import hashlib
import html
import json
import re
from dataclasses import asdict
from pathlib import Path

import genanki

from autoflashcards.models import Block, Card, normalize

# Fixed forever: changing one makes Anki create a second note type on the next import
BASIC_MODEL_ID = 1854201137
CLOZE_MODEL_ID = 1854201138

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
    model = CLOZE_MODEL if card.kind == "cloze" else BASIC_MODEL
    return genanki.Note(
        model=model,
        fields=[_html(card.front), _html(card.back), _html(card.source_label)],
        tags=tags(card),
        guid=note_guid(deck_name, card),
    )


def write_apkg(cards: list[Card], deck_name: str, out: Path) -> None:
    deck = genanki.Deck(_stable_id(deck_name), deck_name)
    for card in cards:
        deck.add_note(to_note(deck_name, card))
    genanki.Package(deck).write_to_file(str(out))


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
    Excel and Notepad read the UTF-8 as Windows-1252 ("·" shows as "Â·")."""
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        f.write(_CSV_HEADER)
        writer = csv.writer(f, lineterminator="\n")
        for card in cards:
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
