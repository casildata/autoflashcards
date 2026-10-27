"""Structure stage on hand-built Lines, one layout case per test."""

from autoflashcards.models import Line
from autoflashcards.structure import to_blocks

BODY = 10.0


def line(text, top, page=1, size=BODY, bold=False, x0=72, x1=None, box_right=None):
    return Line(text, page, size, bold, x0, top, top + size, "", x1, box_right)


def blocks(lines):
    return [(b.kind, b.heading_path, b.text) for b in to_blocks(lines, "x.pdf")]


def test_wrapped_lines_join_and_finished_lines_split():
    result = blocks([
        line("Cells are small and one cell can", 100),
        line("divide into two.", 115),
        line("Tissues: groups of cells.", 130),
        line("Organs: groups of tissues.", 145),
    ])  # fmt: skip
    assert [text for _, _, text in result] == [
        "Cells are small and one cell can divide into two.",
        "Tissues: groups of cells.",
        "Organs: groups of tissues.",
    ]


def test_large_vertical_gap_starts_a_new_paragraph():
    result = blocks([line("first part without a period", 100), line("Second part", 140)])
    assert len(result) == 2


def test_hyphen_at_line_end_is_rejoined():
    result = blocks([line("across the mem-", 100), line("brane.", 115)])
    assert result[0][2] == "across the membrane."


def test_indented_line_continues_a_bullet():
    result = blocks([
        line("• Diffusion: from high to low", 100),
        line("concentration.", 115, x0=86),
        line("Next paragraph after the list.", 130),
    ])  # fmt: skip
    assert result == [
        ("bullet", (), "Diffusion: from high to low concentration."),
        ("paragraph", (), "Next paragraph after the list."),
    ]


def test_unindented_lowercase_line_continues_a_bullet():
    result = blocks([line("1. Carrier: moves molecules across the", 100), line("membrane.", 115)])
    assert result == [("bullet", (), "Carrier: moves molecules across the membrane.")]


def test_bullet_glyphs_and_unmapped_glyphs():
    result = blocks([
        line("• Dash: one", 100),
        line("� Unmapped: two", 115),  # the PDF reader's stand-in for "(cid:N)"
        line("1. Number: three", 130),
        line("b) Letter: four", 145),
        line("Text with a stray � glyph.", 160),
    ])  # fmt: skip
    assert result == [
        ("bullet", (), "Dash: one"),
        ("bullet", (), "Unmapped: two"),
        ("bullet", (), "Number: three"),
        ("bullet", (), "Letter: four"),
        ("paragraph", (), "Text with a stray glyph."),
    ]


def test_ligatures_are_normalized():
    assert blocks([line("ﬁbrous tissue", 100)])[0][2] == "fibrous tissue"


def test_running_headers_footers_and_page_numbers_are_dropped():
    lines = []
    for page in (1, 2, 3):
        lines += [
            line("Course Notes", 30, page),
            line(f"Body text on page {page}.", 100, page),
            line(f"{page}", 750, page),
        ]
    assert [text for _, _, text in blocks(lines)] == [f"Body text on page {p}." for p in (1, 2, 3)]


def test_footers_on_alternate_pages_are_dropped():
    # books put the page number on the left of even pages and the right of odd ones
    body = ["Alpha.", "Beta.", "Gamma.", "Delta.", "Epsilon.", "Zeta."]
    lines = []
    for page, text in enumerate(body, start=1):
        footer = f"{page} © Publisher" if page % 2 == 0 else f"© Publisher {page}"
        lines += [line(text, 100, page), line(footer, 750, page)]
    assert [text for _, _, text in blocks(lines)] == body


def test_bold_lead_is_kept_only_when_it_starts_the_block():
    def lead(text, bold_lead):
        return to_blocks([Line(text, 1, BODY, False, 72, 100, 110, bold_lead)], "x.pdf")[0]

    assert lead("Mitosis divides a cell.", "Mitosis").bold_lead == "Mitosis"
    assert lead("• Mitosis divides a cell.", "Mitosis").bold_lead == "Mitosis"  # after marker
    assert lead("A cell divides.", "cell").bold_lead == ""


def test_heading_levels_from_size_then_bold():
    result = blocks([
        line("Chapter", 50, size=20),
        line("Section", 80, size=14),
        line("Subsection", 100, bold=True),
        line("Body.", 115),
        line("Other Section", 140, size=14),
        line("More body.", 160),
    ])  # fmt: skip
    assert result == [
        ("heading", (), "Chapter"),
        ("heading", ("Chapter",), "Section"),
        ("heading", ("Chapter", "Section"), "Subsection"),
        ("paragraph", ("Chapter", "Section", "Subsection"), "Body."),
        ("heading", ("Chapter",), "Other Section"),
        ("paragraph", ("Chapter", "Other Section"), "More body."),
    ]


def test_bold_lines_that_are_not_headings():
    result = blocks([
        line("Osmosis: water movement.", 100, bold=True),  # ends in punctuation
        line("• Bold bullet", 115, bold=True),
    ])  # fmt: skip
    assert [kind for kind, _, _ in result] == ["paragraph", "bullet"]


def test_heading_wrapped_onto_two_lines():
    result = blocks([
        line("Introduction to Cellular", 50, size=20),
        line("Respiration", 74, size=20),
        line("Cells release energy from glucose in a series of steps.", 110),
    ])  # fmt: skip
    assert [(kind, path) for kind, path, _ in result] == [
        ("heading", ()),
        ("paragraph", ("Introduction to Cellular Respiration",)),
    ]
    assert result[0][2] == "Introduction to Cellular Respiration"


def test_stacked_bold_lines_stay_separate_headings():
    result = blocks([
        line("Daqing Chen", 50, bold=True),
        line("Kun Guo", 63, bold=True),
        line("The authors study customer segmentation in online retail.", 90),
    ])  # fmt: skip
    assert [text for kind, _, text in result if kind == "heading"] == ["Daqing Chen", "Kun Guo"]


def test_sentence_continues_across_a_page_break():
    result = to_blocks([
        line("The cycle has eight", 700, page=1),
        line("steps in total.", 72, page=2),
        line("New paragraph.", 87, page=2),
    ], "x.pdf")  # fmt: skip
    assert [(b.page, b.text) for b in result] == [
        (1, "The cycle has eight steps in total."),  # a block's page is where it starts
        (2, "New paragraph."),
    ]


def test_short_line_then_capital_starts_a_new_item():
    # slide bullets drawn as pictures: no marker, no period, but the first line stops short
    result = blocks([
        line("The subject is large", 100, x0=72, x1=180, box_right=400),
        line("Life is studied on many levels, from cells and the molecules in", 115, x1=400,
             box_right=400),
        line("them to the planet", 130, x1=170, box_right=400),
    ])  # fmt: skip
    assert [text for _, _, text in result] == [
        "The subject is large",
        "Life is studied on many levels, from cells and the molecules in them to the planet",
    ]


def test_definition_line_starts_a_new_item():
    result = blocks([
        line("Smallest unit of organization that can perform all of the activities", 100,
             x1=400, box_right=400),
        line("Cell theory = all organisms are made of cells", 115, x1=300, box_right=400),
    ])  # fmt: skip
    assert len(result) == 2


def test_body_size_is_found_per_page():
    # a handout page whose slides print bullets at 12pt, in a file whose body text is 9pt
    bullet = "Short slide bullet with no period"
    result = blocks(
        [line(bullet, 100 + 30 * i, page=1, size=12) for i in range(6)]
        + [line("Title", 80, page=2, size=16)]
        + [line(bullet, 100 + 30 * i, page=2, size=9) for i in range(9)]
    )
    assert [text for kind, _, text in result if kind == "heading"] == ["Title"]


def test_large_prose_that_goes_on_is_not_a_heading():
    result = blocks([
        line("Several properties are found", 100, size=14),
        line("in all living things", 118, size=14),
        line("A body sentence that sets the body size for the rest of this page, and more.", 150),
        line("A body sentence that sets the body size for the rest of this page, and more.", 165),
    ])  # fmt: skip
    assert result[0][0] == "paragraph"


def test_empty_input():
    assert to_blocks([], "x.pdf") == []
