"""Anki export. IDs are fixed or derived from content, so re-imports update instead of duplicate."""

import hashlib
import html
import re
from pathlib import Path

import genanki

from autoflashcards.models import Card

# Fixed forever: changing it makes Anki create a second note type on the next import
BASIC_MODEL_ID = 1854201137

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
    css=(
        ".card { font-family: sans-serif; font-size: 20px; text-align: center; }\n"
        ".source { margin-top: 1.5em; font-size: 12px; color: #888; }"
    ),
)


def _stable_id(text: str) -> int:
    """Positive 31-bit integer from text, for Anki deck IDs."""
    return int(hashlib.sha256(text.encode()).hexdigest(), 16) % (1 << 31)


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _tag(text: str) -> str:
    """Anki tags can't contain spaces; keep letters, digits, - and _."""
    return re.sub(r"[^\w-]+", "_", text.lower()).strip("_")


def note_guid(deck_name: str, card: Card) -> str:
    # The front identifies a card; a fixed typo in the back updates the same note
    return genanki.guid_for(deck_name, _normalize(card.front))


def to_note(deck_name: str, card: Card) -> genanki.Note:
    tags = [f"afg::rule::{card.rule}"]
    heading_tag = "::".join(t for t in map(_tag, card.heading_path) if t)
    if heading_tag:
        tags.append(heading_tag)
    return genanki.Note(
        model=BASIC_MODEL,
        fields=[html.escape(card.front), html.escape(card.back), html.escape(card.source_label)],
        tags=tags,
        guid=note_guid(deck_name, card),
    )


def write_apkg(cards: list[Card], deck_name: str, out: Path) -> int:
    """Write the deck and return the number of notes in it."""
    deck = genanki.Deck(_stable_id(deck_name), deck_name)
    seen: set[str] = set()
    for card in cards:
        note = to_note(deck_name, card)
        if note.guid in seen:  # same front twice: one note per ID, first one wins
            continue
        seen.add(note.guid)
        deck.add_note(note)
    genanki.Package(deck).write_to_file(str(out))
    return len(deck.notes)
