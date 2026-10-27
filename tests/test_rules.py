import pytest

from autoflashcards.models import Block
from autoflashcards.rules import bold_lead, definition_sentence, generate, term_colon


def _card(text, kind="bullet"):
    cards = term_colon(Block(kind, text, "x.md", ("A", "B")))
    return (cards[0].front, cards[0].back) if cards else None


def test_term_and_definition():
    assert _card("Osmosis: movement of water.") == ("Osmosis", "movement of water.")


def test_space_before_colon():
    assert _card("Active transport : uses ATP.") == ("Active transport", "uses ATP.")


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
    ],
)
def test_definition_becomes_cloze(cloze):
    text = cloze.replace("{{c1::", "").replace("}}", "")
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


# generate


def test_reference_sections_are_skipped():
    blocks = [
        Block("paragraph", "Osmosis: water.", "x.pdf", ("Ch1",)),
        Block("paragraph", "Hoboken, NJ: John Wiley & Sons.", "x.pdf", ("Ch1", "References")),
    ]
    assert [c.front for c in generate(blocks)] == ["Osmosis"]


def test_first_matching_rule_wins():
    # matches bold_lead and definition_sentence; only bold_lead's card is kept
    block = Block("paragraph", "Mitosis is a type of cell division.", "x.md", bold_lead="Mitosis")
    assert [c.rule for c in generate([block])] == ["bold_lead"]


def test_rule_selection():
    block = Block("paragraph", "Mitosis is a type of cell division.", "x.md", bold_lead="Mitosis")
    assert [c.rule for c in generate([block], ["definition_sentence"])] == ["definition_sentence"]
    assert generate([block], ["term_colon"]) == []
