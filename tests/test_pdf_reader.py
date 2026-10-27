import pytest

from autoflashcards.readers import read

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
]  # fmt: skip


def test_lecture_pdf_blocks(cells_pdf):
    blocks = read(cells_pdf)
    assert [(b.page, b.kind, b.heading_path, b.text) for b in blocks] == EXPECTED
    assert {b.source for b in blocks} == {"cells.pdf"}


def test_two_columns_are_read_left_column_first(two_column_pdf):
    blocks = read(two_column_pdf)
    assert [(b.kind, b.text) for b in blocks] == [
        ("heading", "Enzymes"),
        ("paragraph", "Enzyme: a protein that speeds up a chemical reaction."),
        ("paragraph", "Substrate: the molecule an enzyme acts on."),
        ("paragraph", "Active site: the region where the substrate binds."),
        ("paragraph", "Inhibitor: a molecule that slows an enzyme down."),
    ]


def test_damaged_pdf_is_a_clear_error(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.7\nnot really a pdf")
    with pytest.raises(ValueError, match="can't read bad.pdf"):
        read(bad)
