"""Round-trip: open the .apkg the way Anki does (a zip holding a SQLite collection)."""

import sqlite3
import zipfile
from dataclasses import replace

from autoflashcards.export import BASIC_MODEL_ID, write_apkg
from autoflashcards.models import Card

CARDS = [
    Card("Osmosis", "movement of water", "term_colon", "cells.md", ("Cell Biology", "Transport")),
    Card("Diffusion", "high to low <conc>", "term_colon", "cells.md", (), page=4),
]


def _notes(apkg, tmp_path):
    with zipfile.ZipFile(apkg) as z:
        db = z.extract("collection.anki2", tmp_path / "unzipped")
    with sqlite3.connect(db) as con:
        rows = con.execute("SELECT guid, mid, flds, tags FROM notes ORDER BY id").fetchall()
    return [(guid, mid, flds.split("\x1f"), tags.split()) for guid, mid, flds, tags in rows]


def test_fields_tags_and_model(tmp_path):
    out = tmp_path / "deck.apkg"
    assert write_apkg(CARDS, "Bio", out) == 2
    (_, mid1, f1, t1), (_, _, f2, t2) = _notes(out, tmp_path)

    assert mid1 == BASIC_MODEL_ID
    assert f1 == ["Osmosis", "movement of water", "cells.md · Cell Biology › Transport"]
    assert sorted(t1) == ["afg::rule::term_colon", "cell_biology::transport"]
    assert f2 == ["Diffusion", "high to low &lt;conc&gt;", "cells.md · p.4"]  # HTML escaped
    assert t2 == ["afg::rule::term_colon"]


def test_ids_are_stable_across_runs_and_back_edits(tmp_path):
    write_apkg(CARDS, "Bio", tmp_path / "a.apkg")
    edited = [replace(CARDS[0], back="fixed typo"), CARDS[1]]
    write_apkg(edited, "Bio", tmp_path / "b.apkg")

    guids_a = [n[0] for n in _notes(tmp_path / "a.apkg", tmp_path / "a")]
    guids_b = [n[0] for n in _notes(tmp_path / "b.apkg", tmp_path / "b")]
    assert guids_a == guids_b


def test_same_front_is_one_note(tmp_path):
    dup = replace(CARDS[0], back="another back")
    assert write_apkg([CARDS[0], dup], "Bio", tmp_path / "deck.apkg") == 1
