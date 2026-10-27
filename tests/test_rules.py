import pytest

from autoflashcards.models import Block
from autoflashcards.rules import generate, term_colon


def _card(text, kind="bullet"):
    cards = term_colon(Block(kind, text, "x.md", ("A", "B")))
    return (cards[0].front, cards[0].back) if cards else None


def test_term_and_definition():
    assert _card("Osmosis: movement of water.") == ("Osmosis", "movement of water.")


def test_space_before_colon():
    assert _card("Active transport : uses ATP.") == ("Active transport", "uses ATP.")


def test_card_keeps_source_and_rule():
    (card,) = term_colon(Block("bullet", "Osmosis: water.", "x.md", ("A", "B"), page=3))
    assert (card.rule, card.source, card.heading_path, card.page) == (
        "term_colon",
        "x.md",
        ("A", "B"),
        3,
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
    ],
)
def test_not_a_definition(text):
    assert _card(text) is None


def test_reference_sections_are_skipped():
    blocks = [
        Block("paragraph", "Osmosis: water.", "x.pdf", ("Ch1",)),
        Block("paragraph", "Hoboken, NJ: John Wiley & Sons.", "x.pdf", ("Ch1", "References")),
    ]
    assert [c.front for c in generate(blocks)] == ["Osmosis"]


def test_headings_are_skipped():
    assert _card("Transport: an overview", kind="heading") is None
