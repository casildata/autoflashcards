import pytest

from autoflashcards.dedupe import dedupe
from autoflashcards.readers import read
from autoflashcards.readers.pdf import _text
from autoflashcards.rules import generate

T, CB, MP, ORG = "Transport", "Cell Biology", "Membrane Proteins", "Organelles"

# Every block from the generated lecture PDF, in order: (page, kind, heading path, text)
EXPECTED = [
    (1, "heading", (), CB),
    (1, "paragraph", (CB,), "Cells are the basic unit of life. Every living thing is made of one "
     "or more cells, and new cells come only from existing cells."),
    (1, "heading", (CB,), T),
    (1, "paragraph", (CB, T), "Osmosis: movement of water across a semipermeable membrane."),
    (1, "bullet", (CB, T), "Diffusion: net movement of particles from high to low "
     "concentration, without energy input."),
    (1, "bullet", (CB, T), "Active transport: movement against a gradient that uses ATP."),
    (2, "heading", (CB, T), MP),
    (2, "bullet", (CB, T, MP), "Channel protein: forms a pore that lets specific ions pass."),
    (2, "bullet", (CB, T, MP), "Carrier protein: changes shape to move a molecule across the "
     "membrane."),
    (3, "heading", (CB,), ORG),
    (3, "paragraph", (CB, ORG), "Mitochondrion: the site of aerobic respiration."),
    (3, "paragraph", (CB, ORG), "Ribosome: assembles proteins from amino acids."),
    (3, "paragraph", (CB, ORG), "Lysosome breaks down waste inside the cell."),
]  # fmt: skip


def test_lecture_pdf_blocks(cells_pdf):
    blocks = read(cells_pdf)
    assert [(b.page, b.kind, b.heading_path, b.text) for b in blocks] == EXPECTED
    assert {b.source for b in blocks} == {"cells.pdf"}


def test_bold_lead_text(cells_pdf):
    leads = {b.text.split()[0]: b.bold_lead for b in read(cells_pdf) if b.kind != "heading"}
    assert leads["Osmosis:"] == "Osmosis:"
    assert leads["Lysosome"] == "Lysosome"
    assert leads["Mitochondrion:"] == ""  # not bold


def test_two_columns_are_read_left_column_first(two_column_pdf):
    blocks = read(two_column_pdf)
    assert [(b.kind, b.text) for b in blocks] == [
        ("heading", "Enzymes"),
        ("paragraph", "Enzyme: a protein that speeds up a chemical reaction."),
        ("paragraph", "Substrate: the molecule an enzyme acts on."),
        ("paragraph", "Active site: the region where the substrate binds."),
        ("paragraph", "Inhibitor: a molecule that slows an enzyme down."),
    ]


def test_handout_slides_are_read_one_by_one(handout_pdf):
    # left and right slides share line heights; each slide is read whole, top row first
    cards, _ = dedupe(generate(read(handout_pdf)))
    assert [(c.front, c.back.split("\n")) for c in cards] == [
        ("Mitosis", ["Divides one nucleus into two", "Keeps the chromosome number"]),
        ("Meiosis", ["Makes four sex cells", "Halves the chromosome number"]),
        ("Cytokinesis", ["Splits the cytoplasm", "Follows mitosis"]),
        ("Interphase", ["The cell grows", "DNA is copied"]),
    ]


def test_slide_deck_cards(slides_pdf):
    cards, _ = dedupe(generate(read(slides_pdf)))
    assert [(c.rule, c.front, c.back.split("\n")) for c in cards] == [
        (
            "slide_title_bullets",
            "Phagocytes",
            [  # first 3 of the slide's 4 bullets
                "White blood cells that engulf pathogens",
                "Include neutrophils and macrophages",
                "Found in blood and in body tissues",
            ],
        ),
        (
            "bold_term_bullets",
            "Macrophages",
            ["Large phagocytes that live in tissues", "Present antigens to T cells"],
        ),
        ("bold_term_bullets", "Neutrophils", ["Most abundant white blood cells"]),
        ("term_colon", "Cytokines", ["signal molecules that recruit immune cells"]),
        ("term_colon", "Interferons", ["proteins that interfere with viral replication"]),
    ]  # no cards from the "43.1" divider, the "Image of…" slide or the "Thanks!" slide


def test_section_numbers_are_not_headings(slides_pdf):
    blocks = read(slides_pdf)
    assert "43.1" not in [b.text for b in blocks if b.kind == "heading"]
    assert all("43.1" not in b.heading_path for b in blocks)


def _char(text, x0, x1, size=14.0):
    return {
        "text": text, "x0": x0, "x1": x1, "top": 100.0, "bottom": 100 + size, "doctop": 100.0,
        "size": size, "fontname": "Calibri", "upright": True, "width": x1 - x0, "height": size,
    }  # fmt: skip


def test_spaces_from_gaps_when_letter_boxes_are_accurate():
    # a stray space character inside "fi nancial", as in some typeset PDFs, is ignored
    chars = [_char("ﬁ", 0, 6), _char(" ", 3, 6), _char("n", 6, 12), _char("e", 18, 24)]
    assert _text(chars) == "fin e"  # pdfplumber also expands the ligature


def test_space_characters_used_when_letter_boxes_overlap():
    # PowerPoint exports: each box is wider than the letter's advance, so gaps are negative
    chars = [_char("o", 0, 13), _char("f", 8, 18), _char(" ", 14, 22), _char("t", 20, 30)]
    assert _text(chars) == "of t"


def test_damaged_pdf_is_a_clear_error(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.7\nnot really a pdf")
    with pytest.raises(ValueError, match="can't read bad.pdf"):
        read(bad)
