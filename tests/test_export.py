"""Round-trip: open the .apkg the way Anki does (a zip holding a SQLite collection)."""

import csv
import json
import sqlite3
import zipfile
from dataclasses import replace

from autoflashcards.export import (
    BASIC_MODEL_ID,
    CLOZE_MODEL_ID,
    note_guid,
    write_apkg,
    write_csv,
    write_json,
)
from autoflashcards.models import Block, Card

CLOZE = "{{c1::Cells}} are the unit of life."
CARDS = [
    Card("Osmosis", "movement of water", "term_colon", "cells.md", ("Cell Biology", "Transport")),
    Card("Diffusion", "high to low <conc>", "term_colon", "cells.md", (), page=4),
    Card(CLOZE, "", "definition_sentence", "cells.md", (), page=1, kind="cloze"),
]


def _notes(apkg, tmp_path):
    with zipfile.ZipFile(apkg) as z:
        db = z.extract("collection.anki2", tmp_path / "unzipped")
    with sqlite3.connect(db) as con:
        rows = con.execute("SELECT guid, mid, flds, tags FROM notes ORDER BY id").fetchall()
    return [(guid, mid, flds.split("\x1f"), tags.split()) for guid, mid, flds, tags in rows]


def test_fields_tags_and_models(tmp_path):
    out = tmp_path / "deck.apkg"
    write_apkg(CARDS, "Bio", out)
    (_, mid1, f1, t1), (_, mid2, f2, t2), (_, mid3, f3, t3) = _notes(out, tmp_path)

    assert mid1 == mid2 == BASIC_MODEL_ID
    assert f1 == ["Osmosis", "movement of water", "cells.md · Cell Biology › Transport"]
    assert sorted(t1) == ["afg::rule::term_colon", "cell_biology::transport"]
    assert f2 == ["Diffusion", "high to low &lt;conc&gt;", "cells.md · p.4"]  # HTML escaped
    assert t2 == ["afg::rule::term_colon"]
    assert mid3 == CLOZE_MODEL_ID
    assert f3 == ["{{c1::Cells}} are the unit of life.", "", "cells.md · p.1"]
    assert t3 == ["afg::rule::definition_sentence"]


def test_bullet_backs_show_one_bullet_per_line(tmp_path):
    card = Card("Protein kinases", "Add phosphates\nWork in <cascades>", "bold_term_bullets", "x")
    write_apkg([card], "Bio", tmp_path / "deck.apkg")
    ((_, _, fields, _),) = _notes(tmp_path / "deck.apkg", tmp_path)
    assert fields[1] == "Add phosphates<br>Work in &lt;cascades&gt;"


def test_ids_are_stable_across_runs_and_back_edits(tmp_path):
    write_apkg(CARDS, "Bio", tmp_path / "a.apkg")
    edited = [replace(CARDS[0], back="fixed typo"), *CARDS[1:]]
    write_apkg(edited, "Bio", tmp_path / "b.apkg")

    guids_a = [n[0] for n in _notes(tmp_path / "a.apkg", tmp_path / "a")]
    guids_b = [n[0] for n in _notes(tmp_path / "b.apkg", tmp_path / "b")]
    assert guids_a == guids_b


def test_csv_for_anki_text_import(tmp_path):
    out = tmp_path / "deck.csv"
    write_csv(CARDS, "Bio", out)
    # a BOM, so Excel and Notepad read "·" and "›" as UTF-8 instead of Windows-1252
    assert out.read_bytes().startswith(b"\xef\xbb\xbf#separator:comma")
    lines = out.read_text(encoding="utf-8-sig").splitlines()
    assert lines[:7] == [
        "#separator:comma",
        "#html:true",
        "#columns:Front,Back,Tags,Note type,Deck,ID",
        "#tags column:3",
        "#notetype column:4",
        "#deck column:5",
        "#guid column:6",
    ]
    rows = list(csv.reader(lines[7:]))
    assert rows[0] == [
        "Osmosis",
        "movement of water<br><small>cells.md · Cell Biology › Transport</small>",
        "afg::rule::term_colon cell_biology::transport",
        "Basic",
        "Bio",
        note_guid("Bio", CARDS[0]),  # same ID as the .apkg note
    ]
    assert rows[1][1].startswith("high to low &lt;conc&gt;")
    assert rows[2][0] == "{{c1::Cells}} are the unit of life."
    assert rows[2][3:5] == ["Cloze", "Bio"]


def test_json_lists_blocks_cards_and_drops(tmp_path):
    out = tmp_path / "deck.json"
    blocks = [Block("bullet", "Osmosis: movement of water", "cells.md")]
    write_json(blocks, CARDS[:1], [(CARDS[1], "too long")], out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["blocks"][0]["text"] == "Osmosis: movement of water"
    assert data["cards"][0]["source_label"] == "cells.md · Cell Biology › Transport"
    assert data["removed"][0]["reason"] == "too long"
