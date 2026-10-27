import re

import pytest

from autoflashcards.models import Block
from autoflashcards.rules import (
    bold_lead,
    bold_term_bullets,
    definition_sentence,
    generate,
    slide_title_bullets,
    term_colon,
)


def _card(text, kind="bullet"):
    cards = term_colon(Block(kind, text, "x.md", ("A", "B")))
    return (cards[0].front, cards[0].back) if cards else None


def test_term_and_definition():
    assert _card("Osmosis: movement of water.") == ("Osmosis", "movement of water.")


def test_space_before_colon():
    assert _card("Active transport : uses ATP.") == ("Active transport", "uses ATP.")


@pytest.mark.parametrize("separator", ["=", "→", "->", " = ", " → "])
def test_slide_separators(separator):
    assert _card(f"Ligand{separator}signal molecule") == ("Ligand", "signal molecule")


def test_card_keeps_source_and_rule():
    (card,) = term_colon(Block("bullet", "Osmosis: water.", "x.md", ("A", "B"), page=3))
    assert (card.rule, card.source, card.heading_path, card.page, card.kind) == (
        "term_colon",
        "x.md",
        ("A", "B"),
        3,
        "basic",
    )


@pytest.mark.parametrize(
    "text",
    [
        "Note: osmosis is a special case of diffusion.",  # label, not a term
        "See https://example.org for diagrams.",  # URL colon has no space after it
        "Lab starts at 10:30 sharp.",  # time
        "The most important things to remember are these: a and b.",  # front too long
        "No colon here at all.",
        "Trailing colon:",
        "Keywords: online retail; data mining",
        "Figure 3: Project diagram.",
        "Table 2: Variables in the dataset.",
        "Fig. 4: Distribution by cluster.",
        "198: page number as the term",
        "1970s: research suggests bacteria signal to one another",  # a decade
        "Example → steroid hormones",
        "E-mail: someone@example.org",
        "2011 was 18.3 (= 406/22)",  # cut mid-formula: unbalanced parentheses
    ],
)
def test_not_a_definition(text):
    assert _card(text) is None


def test_headings_are_skipped():
    assert _card("Transport: an overview", kind="heading") is None


# bold_lead


def _lead(text, lead):
    cards = bold_lead(Block("paragraph", text, "x.pdf", bold_lead=lead))
    return (cards[0].front, cards[0].back) if cards else None


def test_bold_term_then_text():
    assert _lead("Mitosis divides a cell into two.", "Mitosis") == (
        "Mitosis",
        "divides a cell into two.",
    )


def test_bold_term_with_dash():
    assert _lead("Lysosome — breaks down cell waste.", "Lysosome") == (
        "Lysosome",
        "breaks down cell waste.",
    )


@pytest.mark.parametrize(
    ("text", "lead"),
    [
        ("Osmosis: movement of water.", "Osmosis"),  # term_colon's job
        ("Whole line in bold", "Whole line in bold"),
        ("Mitosis divides.", "Mitosis"),  # too little after the term
        ("200 © 2012 Macmillan Publishers Ltd.", "200"),  # bold page number
        ("No bold here at all.", ""),
    ],
)
def test_not_a_bold_lead(text, lead):
    assert _lead(text, lead) is None


# definition_sentence


def _cloze(text):
    return [c.front for c in definition_sentence(Block("paragraph", text, "x.md"))]


@pytest.mark.parametrize(
    "cloze",
    [
        "A {{c1::ribosome}} is a structure that builds proteins.",
        "{{c1::Cells}} are the basic unit of life.",
        "The {{c1::cell membrane}} is defined as a lipid barrier.",
        "{{c1::Entropy}} refers to the disorder of a system.",
        "{{c1::Napoleon}} was a French military leader.",
        "{{c1::Homozygous}} means having two identical alleles.",
        "{{c1::Homozygous}} means having two identical alleles, and {{c2::heterozygous}} means "
        "having two different ones.",
        "A {{c1::cation}} is an ion with a positive charge; an {{c2::anion}} is an ion with a "
        "negative charge.",
        "{{c1::Retention}}, the share of customers who come back, is easy to explain.",
    ],
)
def test_definition_becomes_cloze(cloze):
    text = re.sub(r"\{\{c\d::(.+?)\}\}", r"\1", cloze)
    assert _cloze(text) == [cloze]


@pytest.mark.parametrize(
    "text",
    [
        "It is a very small organelle.",  # pronoun subject
        "This is the end of the chapter.",
        "There are a few exceptions to the rule.",
        "evident that there are a few instances.",  # fragment, not a sentence start
        "Mitosis is important for growth.",  # "is" without a defining word after it
        "The SAS procedures proc means and proc sql were used.",  # "means" isn't a cue
        "In biology, a cell is a unit of life.",  # comma before the verb
        "Osmosis is a process.",  # too little after the verb
        "evidence is a strong word here.",  # lowercase start: a fragment
        "Proc means and proc sql were used.",  # "means" before "and" isn't a definition
        "However, the results, as shown below, are mixed.",  # not an appositive term
        "In 2010, a small study, run by one shop, found more.",
        "Cells divide, and it is a slow process.",  # pronoun subject in the second clause
    ],
)
def test_not_a_definition_sentence(text):
    assert _cloze(text) == []


def test_each_defining_sentence_in_a_block():
    text = "Cells are the basic unit of life. It is small. A tissue is a group of cells."
    assert _cloze(text) == [
        "{{c1::Cells}} are the basic unit of life.",
        "A {{c1::tissue}} is a group of cells.",
    ]
    assert {c.kind for c in definition_sentence(Block("paragraph", text, "x.md"))} == {"cloze"}


# bold_term_bullets


def bullet(text, bold=False, path=("Slide",), page=1):
    return Block("bullet", text, "x.pdf", path, page, text if bold else "")


def _bold_term(blocks):
    cards = bold_term_bullets(blocks, 0)
    return (cards[0].front, cards[0].back.split("\n")) if cards else None


def test_bold_bullet_with_explaining_bullets():
    blocks = [
        bullet("Protein kinases", bold=True),
        bullet("Transfer phosphates from ATP to proteins"),
        bullet("Work in cascades"),
        bullet("Protein phosphatases", bold=True),  # the next term: stop
        bullet("Remove phosphates"),
    ]
    assert _bold_term(blocks) == (
        "Protein kinases",
        ["Transfer phosphates from ATP to proteins", "Work in cascades"],
    )


def test_bold_term_back_is_capped():
    blocks = [bullet("Cytokines", bold=True)] + [bullet(f"Fact {n}") for n in range(5)]
    assert _bold_term(blocks)[1] == ["Fact 0", "Fact 1", "Fact 2"]


@pytest.mark.parametrize(
    "follower",
    [
        Block("heading", "Next slide", "x.pdf", ("Slide",), 1),
        bullet("Different slide", page=2),
        bullet("Different section", path=("Other",)),
        Block("paragraph", "A paragraph", "x.pdf", ("Slide",), 1),
    ],
)
def test_bold_term_needs_bullets_right_after_it(follower):
    assert _bold_term([bullet("Ligand", bold=True), follower]) is None


def test_partly_bold_bullet_is_not_a_bold_term():
    term = Block("bullet", "Mitosis divides a cell.", "x.pdf", ("Slide",), 1, "Mitosis")
    assert _bold_term([term, bullet("Happens in body cells")]) is None


# slide_title_bullets


def heading(text, path=()):
    return Block("heading", text, "x.pdf", path, 1)


def _slide(blocks):
    cards = slide_title_bullets(blocks, 0)
    return (cards[0].front, cards[0].back.split("\n"), cards[0].heading_path) if cards else None


def test_slide_title_with_bullets():
    blocks = [
        heading("G protein-coupled receptor", ("Ch11",)),
        bullet("Cell-surface receptors that work with a G protein", path=("Ch11", "GPCR")),
        bullet("Largest family of cell-surface receptors", path=("Ch11", "GPCR")),
        heading("Next slide", ("Ch11",)),
    ]
    assert _slide(blocks) == (
        "G protein-coupled receptor",
        [
            "Cell-surface receptors that work with a G protein",
            "Largest family of cell-surface receptors",
        ],
        ("Ch11", "GPCR"),  # the card sits under its slide title
    )


@pytest.mark.parametrize(
    "blocks",
    [
        [heading("Image of a GPCR pathway"), bullet("Shows the pathway")],
        [heading("Example of signaling"), bullet("Insulin binding")],
        [heading("Thanks!"), bullet("Questions welcome")],
        [heading("Table of contents"), bullet("Signal reception")],
        [heading("Receptors")],  # no bullets
        [heading("Receptors"), Block("paragraph", "Some prose.", "x.pdf", (), 1)],
        [heading("Receptors")] + [bullet(f"Point {n}") for n in range(9)],  # textbook list
        [heading("Receptors"), bullet("GPCR", bold=True), bullet("Uses a G protein")],
        [heading("Transport"), bullet("Osmosis: movement of water"), bullet("Uses no ATP")],
        [heading("A title that is far too long to be a term")],
        [heading("Receptors"), bullet("On the next slide", page=2)],
        [heading("Domains"), Block("paragraph", "13%", "x.pdf", (), 1)],  # a chart label
    ],
)
def test_not_a_slide_title_card(blocks):
    assert _slide(blocks) is None


def test_slide_with_an_example_bullet_still_counts():
    blocks = [
        heading("Intracellular Receptors"),
        bullet("Found in the cytoplasm"),
        bullet("Example → steroid hormones"),
    ]
    assert _slide(blocks)[0] == "Intracellular Receptors"


def test_bullets_drawn_as_pictures_still_count():
    # a slide whose bullet markers are images: its bullets come through as short paragraphs
    blocks = [
        heading("Qualitative"),
        Block("paragraph", "Recorded observations and descriptions", "x.pdf", (), 1),
    ]
    assert _slide(blocks)[:2] == ("Qualitative", ["Recorded observations and descriptions"])


# generate


def test_reference_sections_are_skipped():
    blocks = [
        Block("paragraph", "Osmosis: water.", "x.pdf", ("Ch1",)),
        Block("paragraph", "Hoboken, NJ: John Wiley & Sons.", "x.pdf", ("Ch1", "References")),
    ]
    assert [c.front for c in generate(blocks)] == ["Osmosis"]


def test_only_the_nearest_heading_skips_a_section():
    # a misread "Table of contents" heading above the whole deck mustn't hide it
    blocks = [
        Block("paragraph", "Ligand: signal molecule.", "x.pdf", ("Table of contents", "Receptors")),
        Block("paragraph", "Template: Slidesgo.", "x.pdf", ("Receptors", "Thanks!")),
    ]
    assert [c.front for c in generate(blocks)] == ["Ligand"]


def test_first_matching_rule_wins():
    # matches bold_lead and definition_sentence; only bold_lead's card is kept
    block = Block("paragraph", "Mitosis is a type of cell division.", "x.md", bold_lead="Mitosis")
    assert [c.rule for c in generate([block])] == ["bold_lead"]


def test_rule_selection():
    block = Block("paragraph", "Mitosis is a type of cell division.", "x.md", bold_lead="Mitosis")
    assert [c.rule for c in generate([block], ["definition_sentence"])] == ["definition_sentence"]
    assert generate([block], ["term_colon"]) == []
