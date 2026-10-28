import csv
import io
import itertools
import json
import re
import sqlite3
import zipfile

import pytest
from make_fixtures import (
    CELL_LABELS,
    HEART_LABELS,
    NOTE_COLOR,
    RIBOSOME_LABELS,
    SLIDE_COLOR,
    diagram_picture,
)
from PIL import Image
from typer.testing import CliRunner

from autoflashcards import diagrams
from autoflashcards.cli import app
from autoflashcards.dedupe import dedupe
from autoflashcards.export import (
    DIAGRAM_MODEL,
    DIAGRAM_MODEL_ID,
    DIAGRAM_TYPED_MODEL,
    DIAGRAM_TYPED_MODEL_ID,
    write_apkg,
)

needs_tesseract = pytest.mark.skipif(
    diagrams._tesseract() is None, reason="Tesseract is not installed"
)
runner = CliRunner()


def _diagram(labels=("Nucleus", "Nucleolus", "Cell membrane")) -> diagrams.Diagram:
    boxes = [
        diagrams.Label(text, (10, 10 + 40 * i, 120, 30 + 40 * i)) for i, text in enumerate(labels)
    ]
    return diagrams.Diagram(Image.new("RGB", (200, 150), "white"), boxes, "cells.pdf", 3, 1)


@pytest.mark.parametrize(
    "text",
    ["Nucleus", "Cell membrane", "Rough ER", "cis Golgi", "Ions or small molecules"],
)
def test_labels(text):
    assert diagrams._is_label(text)


@pytest.mark.parametrize(
    "text",
    [
        "Cells are the basic unit of life in every organism.",  # sentence
        "of two types of cells:",
        "Exploring cell junctions in",  # wrapped line
        "Figure 6.3",
        "(a) Phagocytosis",  # panel letter
        "0.5 µm",  # scale bar
        "6.1",
        "yding@example.edu",
        "Cy",  # OCR fragment
    ],
)
def test_not_labels(text):
    assert not diagrams._is_label(text)


def test_stacked_lines_make_one_label():
    lines = [
        ("Nuclear", (100, 100, 140, 110)),
        ("envelope", (100, 113, 148, 123)),
        ("oxygen-", (300, 100, 340, 110)),
        ("using", (300, 113, 330, 123)),
        ("Ribosome", (100, 160, 150, 170)),  # far below: its own label
    ]
    assert [text for text, _ in diagrams._stacked(lines)] == [
        "Nuclear envelope",
        "oxygen-using",
        "Ribosome",
    ]


def test_text_layer_diagram(diagram_pdf):
    found = diagrams.read_pdf(diagram_pdf, warn=print)
    drawn = [d for d in found if d.page == 1]
    # the ruled table on page 1 isn't a diagram
    assert len(drawn) == 1
    assert sorted(label.text for label in drawn[0].labels) == sorted(t for t, *_ in CELL_LABELS)
    width, height = drawn[0].image.size
    for label in drawn[0].labels:
        x0, top, x1, bottom = label.box
        assert 0 <= x0 < x1 <= width and 0 <= top < bottom <= height


def test_figure_in_strips_is_drawn_whole_without_the_slide(diagram_pdf):
    (slide,) = [d for d in diagrams.read_pdf(diagram_pdf, warn=print) if d.page == 3]
    assert [label.text for label in slide.labels] == RIBOSOME_LABELS
    # 10 strips of 20 points, at 150 dpi: the whole figure, not one strip
    width, height = slide.image.size
    assert height >= 200 * diagrams.RESOLUTION / 72
    # the slide picture and the sticky note under the figure are left out
    colors = {color for _, color in slide.image.getcolors(width * height)}
    near = lambda a, b: all(abs(x - y) < 20 for x, y in zip(a, b, strict=True))  # noqa: E731
    assert not any(near(c, SLIDE_COLOR) or near(c, NOTE_COLOR) for c in colors)


def test_strips_and_grids_are_joined():
    strips = [(10, 10 + 20 * n, 210, 30 + 20 * n) for n in range(5)]
    grid = [
        (300 + 50 * c, 10 + 50 * r, 350 + 50 * c, 60 + 50 * r) for r in range(2) for c in range(2)
    ]
    apart = [(10, 200, 50, 240), (52, 200, 92, 250)]  # touching, but not edge to edge
    assert (
        diagrams._tiles(strips + grid + apart) == [(10, 10, 210, 110), (300, 10, 400, 110)] + apart
    )


def test_pictures_without_tesseract_warn_once(diagram_pdf, monkeypatch):
    monkeypatch.setattr(diagrams, "_tesseract", lambda: None)
    warnings = []
    found = diagrams.read_pdf(diagram_pdf, warn=warnings.append)
    assert [d.page for d in found] == [1, 3]  # the text-layer diagrams still work
    assert len(warnings) == 1 and "Tesseract" in warnings[0]


@needs_tesseract
def test_labels_inside_a_picture_are_read_with_ocr(diagram_pdf, tmp_path):
    pictured = [d for d in diagrams.read_pdf(diagram_pdf, warn=print) if d.page == 2]
    # the picture bullets on page 2 aren't diagrams
    assert len(pictured) == 1
    assert sorted(label.text for label in pictured[0].labels) == sorted(HEART_LABELS)

    diagram_picture().save(tmp_path / "heart.png")
    (from_file,) = diagrams.read_image(tmp_path / "heart.png")
    assert sorted(label.text for label in from_file.labels) == sorted(HEART_LABELS)


def test_one_note_per_diagram_with_an_independent_box_per_label():
    (card,), media = diagrams.cards([_diagram()])
    assert card.front == "cells.pdf p.3 figure 1"
    assert card.back == "Nucleus\nNucleolus\nCell membrane"
    assert (card.kind, card.rule, card.media) == ("diagram", "diagram", tuple(media))
    # label 1 is at (10, 10)-(120, 30) in a 200 x 150 image, plus 3 pixels of padding.
    # Each box has its own cloze number, so Anki's editor resizes it on its own
    shapes = card.occlusion.split("<br>")
    assert shapes[0] == (
        "{{c1::image-occlusion:rect:left=0.0350:top=0.0467:width=0.5800:height=0.1733:oi=1}}"
    )
    assert [s[:5] for s in shapes] == ["{{c1:", "{{c2:", "{{c3:"]


def test_answers_are_escaped():
    (card,), _ = diagrams.cards([_diagram(("Na+ <channel>", "K & Cl"))])
    assert card.answers == "{{c1::Na+ &lt;channel&gt;}}<br>{{c2::K &amp; Cl}}"
    assert not card.typed


def test_long_label_lists_are_kept():
    many = _diagram(tuple(f"Structure number {n}" for n in range(30)))
    cards, _ = diagrams.cards([many])
    kept, removed = dedupe(cards)
    assert len(kept) == 1 and not removed


def _apkg_notes(apkg, tmp_path):
    with zipfile.ZipFile(apkg) as z:
        db = z.extract("collection.anki2", tmp_path / "unzipped")
        packed = set(json.loads(z.read("media")).values())
    with sqlite3.connect(db) as con:
        notes = con.execute("SELECT mid, flds FROM notes").fetchall()
        cards = con.execute("SELECT count(*) FROM cards").fetchone()[0]
        models = json.loads(con.execute("SELECT models FROM col").fetchone()[0])
    return packed, notes, cards, models


IO_FIELDS = ["Occlusion", "Image", "Header", "Back Extra", "Comments"]


def test_apkg_is_an_anki_image_occlusion_note(tmp_path):
    cards, media = diagrams.cards([_diagram()])
    write_apkg(cards, "Bio", tmp_path / "deck.apkg", media)
    packed, notes, card_count, models = _apkg_notes(tmp_path / "deck.apkg", tmp_path)
    assert packed == set(media)
    # Anki opens its occlusion editor for note types marked as its Image Occlusion kind
    model = models[str(DIAGRAM_MODEL_ID)]
    assert model["name"] == "Image Occlusion (autoflashcards)"
    assert model["originalStockKind"] == 6 and model["type"] == 1  # cloze
    assert [f["name"] for f in model["flds"]] == [*IO_FIELDS, "Image Labels", "Source"]
    qfmt, afmt = model["tmpls"][0]["qfmt"], model["tmpls"][0]["afmt"]
    assert "type:" not in qfmt + afmt
    # the back shows the label of this card's box, which text to speech can read
    assert "{{cloze-only:Image Labels}}" in afmt and "cloze-only" not in qfmt
    # Anki's editor warns about clozes in Image Labels unless the front has it with `cloze:`;
    # this renders only when Image Labels is empty, so the front shows no label
    assert "{{^Image Labels}}{{cloze:Image Labels}}{{/Image Labels}}" in qfmt
    assert '<div class="source">{{Source}}</div>' in afmt
    ((mid, fields),) = notes
    occlusion, image, header, back_extra, comments, answers, source = fields.split("")
    assert mid == DIAGRAM_MODEL_ID
    assert occlusion == cards[0].occlusion
    assert image == f'<img src="{cards[0].media[0]}">'
    assert back_extra == ""  # the label list, with OCR's misreads, isn't on every card
    assert answers == "{{c1::Nucleus}}<br>{{c2::Nucleolus}}<br>{{c3::Cell membrane}}"
    assert source == "cells.pdf · p.3"
    assert card_count == 3  # one note, a card per box


def test_apkg_typed_answers(tmp_path):
    cards, media = diagrams.cards([_diagram()], typed=True)
    write_apkg(cards, "Bio", tmp_path / "deck.apkg", media)
    _, notes, card_count, models = _apkg_notes(tmp_path / "deck.apkg", tmp_path)
    model = models[str(DIAGRAM_TYPED_MODEL_ID)]
    assert model["name"] == "Image Occlusion (autoflashcards, type in the answer)"
    assert model["originalStockKind"] == 6
    assert [f["name"] for f in model["flds"]] == [*IO_FIELDS, "Image Labels", "Source"]
    assert "{{type:cloze:Image Labels}}" in model["tmpls"][0]["qfmt"]
    assert "cloze-only" not in model["tmpls"][0]["afmt"]  # the typing check shows the label
    ((mid, fields),) = notes
    *_, back_extra, comments, answers, source = fields.split("")
    assert mid == DIAGRAM_TYPED_MODEL_ID
    # the label of box N is cloze N, one per line
    assert answers == "{{c1::Nucleus}}<br>{{c2::Nucleolus}}<br>{{c3::Cell membrane}}"
    assert back_extra == "" and source == "cells.pdf · p.3"
    assert card_count == 3


def test_a_box_added_in_anki_says_what_answer_to_add():
    # A box drawn in Anki's editor gets a card but no cloze in Image Labels; the card's script
    # then names the box. Anki would read two braces in a row in the script as a field.
    for side in ("qfmt", "afmt"):
        template = DIAGRAM_TYPED_MODEL.templates[0][side]
        script = template.split("{{#Image Labels}}<script>")[1]
        script = script.split("</script>{{/Image Labels}}")[0]
        assert "has no answer yet" in script and ".cloze[data-ordinal]" in script
        # only for Anki's warning: Browse's Preview drops the typing box, answer or not
        assert "!type.textContent.trim()" in script
        assert "{{" not in script and "}}" not in script


def test_a_box_deleted_in_anki_says_how_to_remove_its_card():
    # Anki keeps the card of a deleted box; it shows the figure with no boxes
    for model, side in itertools.product((DIAGRAM_MODEL, DIAGRAM_TYPED_MODEL), ("qfmt", "afmt")):
        template = model.templates[0][side]
        script = template.split('<div id="afg-no-box"></div>\n<script>')[1].split("</script>")[0]
        assert "Tools > Empty Cards" in script
        # the back marks the card's box cloze-highlight, which isn't a deleted box
        assert ".cloze-highlight[data-ordinal]" in script
        # with no line left, Anki adds its own notice, found by its link: one message, not two
        assert 'a[href*="#no-cloze"]' in script and "notice.parentElement.hidden = true" in script
        assert "{{" not in script and "}}" not in script


def test_box_numbers_follow_reading_order():
    # "Right" sits 2 px higher than "Left" on the same line: still one row, read left first
    label = diagrams.Label
    labels = [
        label("Below", (10, 60, 80, 75)),
        label("Right", (200, 14, 260, 29)),
        label("Left", (10, 16, 80, 31)),
    ]
    assert [x.text for x in diagrams._in_order(labels)] == ["Left", "Right", "Below"]


def test_cards_can_show_box_numbers():
    for model in (DIAGRAM_MODEL, DIAGRAM_TYPED_MODEL):
        qfmt, afmt = model.templates[0]["qfmt"], model.templates[0]["afmt"]
        scripts = [s.split("</script>")[0] for s in (qfmt + afmt).split("<script>")[1:]]
        assert all("{{" not in s and "}}" not in s for s in scripts)
        # the back has buttons for the numbers and the masks; the front keeps its masks on
        assert 'id="afg-numbers"' in afmt and 'id="afg-numbers"' not in qfmt
        assert 'id="afg-masks"' in afmt and "afgMasksOff" not in qfmt
        # not Anki's own #toggle, whose state is lost when an edit re-renders the card
        assert 'id="toggle"' not in afmt
        # the button states live on window, which outlives a re-render
        assert "window.afgNumbers ||" in qfmt and "window.afgMasksOff ?" in afmt
    # a box with no answer yet gets its number and an outline, to match the message
    assert "window.afgMissing = n;" in DIAGRAM_TYPED_MODEL.templates[0]["qfmt"]


def test_cli_diagrams(diagram_pdf, tmp_path):
    out = tmp_path / "deck.apkg"
    result = runner.invoke(app, [str(diagram_pdf), "--diagrams", "--out", str(out), "--csv"])
    assert result.exit_code == 0, result.output
    pictures = 1 if diagrams._tesseract() else 0  # page 2's figure needs OCR
    assert f"({2 + pictures} diagram card(s) are in the .apkg only)" in result.output
    _, notes, card_count, _ = _apkg_notes(out, tmp_path)
    labels = len(CELL_LABELS) + len(RIBOSOME_LABELS) + (len(HEART_LABELS) if pictures else 0)
    text_cards = sum(1 for mid, _ in notes if mid != DIAGRAM_MODEL_ID)
    assert len(notes) - text_cards == 2 + pictures
    assert card_count == text_cards + labels
    # the summary counts a card per box, which is what Anki makes
    assert f"and {2 + pictures} diagrams ({labels} cards, one per box) to {out}" in result.output
    assert "Diagram notes need Anki 23.10 or newer." in result.output


def test_read_pdf_reports_each_page(diagram_pdf):
    calls = []
    diagrams.read_pdf(diagram_pdf, warn=lambda m: None, progress=lambda *c: calls.append(c))
    assert calls == [(page, len(calls)) for page in range(1, len(calls) + 1)]


def test_cli_type_answers(diagram_pdf, tmp_path):
    out = tmp_path / "deck.apkg"
    args = [str(diagram_pdf), "--diagrams", "--type-answers", "--out", str(out)]
    assert runner.invoke(app, args).exit_code == 0
    _, notes, _, _ = _apkg_notes(out, tmp_path)
    assert any(mid == DIAGRAM_TYPED_MODEL_ID for mid, _ in notes)
    assert all(mid != DIAGRAM_MODEL_ID for mid, _ in notes)


def test_apkg_leaves_out_images_of_dropped_cards(tmp_path):
    other = _diagram(("Aorta", "Valve"))
    other.image = Image.new("RGB", (200, 150), "pink")
    cards, media = diagrams.cards([_diagram(), other])
    assert len(media) == 2
    write_apkg(cards[:1], "Bio", tmp_path / "deck.apkg", media)
    with zipfile.ZipFile(tmp_path / "deck.apkg") as z:
        assert set(json.loads(z.read("media")).values()) == set(cards[0].media)


def test_simple_image_occlusion_front():
    (card,), media = diagrams.cards([_diagram(('Na+ "channel"', "K & Cl"))])
    (image,) = media
    # label 1 is at (10, 10)-(120, 30) in a 200 x 150 image, plus 3 pixels of padding
    assert card.sio == (
        f'<img class="sio-image" src="{image}">'
        '<div class="sio-rect" style="left: 3.5000%; top: 4.6667%; width: 58.0000%; '
        'height: 17.3333%;" word="Na+ \'channel\'" hint=""></div>'
        '<div class="sio-rect" style="left: 3.5000%; top: 31.3333%; width: 58.0000%; '
        'height: 17.3333%;" word="K &amp; Cl" hint=""></div>'
    )


def test_cli_sio(diagram_pdf, tmp_path):
    out = tmp_path / "deck.apkg"
    args = [str(diagram_pdf), "--diagrams", "--sio", "--out", str(out)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    # the diagrams go to the CSV, not the .apkg
    _, notes, _, _ = _apkg_notes(out, tmp_path)
    assert all(mid != DIAGRAM_MODEL_ID for mid, _ in notes)
    header, rows = (
        (tmp_path / "deck-sio.csv").read_text(encoding="utf-8-sig").split("\n#guid column:5\n")
    )
    assert "#notetype:Image Occlusion Simple (v2)" in header
    first = next(csv.reader(io.StringIO(rows)))
    front, source, words, tags, guid = first
    assert words == "; ".join(sorted(t for t, *_ in CELL_LABELS))
    assert source.startswith(diagram_pdf.name) and tags == "afg::rule::diagram"
    (image,) = re.findall(r'src="([^"]+)"', front)
    assert (tmp_path / "deck-media" / image).is_file()


def test_cli_link_pdf(diagram_pdf, tmp_path):
    out = tmp_path / "deck.apkg"
    args = [str(diagram_pdf), "--diagrams", "--sio", "--link-pdf", "--out", str(out)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "Warning: --link-pdf puts each PDF's full path" in result.output
    header, rows = (
        (tmp_path / "deck-sio.csv").read_text(encoding="utf-8-sig").split("\n#guid column:6\n")
    )
    assert "#columns:Front,Header,HeaderURL_filepdf#page=,Words,Tags,ID" in header
    assert "#tags column:5" in header
    first = next(csv.reader(io.StringIO(rows)))
    assert first[2] == f"{diagram_pdf.resolve().as_uri()}#page=1"


def test_cli_link_pdf_needs_sio(diagram_pdf, tmp_path):
    args = [str(diagram_pdf), "--diagrams", "--link-pdf", "--out", str(tmp_path / "d.apkg")]
    result = runner.invoke(app, args)
    assert result.exit_code == 2 and "--link-pdf needs --sio" in result.output
