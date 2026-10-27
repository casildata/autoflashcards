from autoflashcards.dedupe import MAX_BACK_CHARS, dedupe
from autoflashcards.models import Card


def card(front, back="a definition", kind="basic"):
    return Card(front, back, "term_colon", "x.md", kind=kind)


def reasons(cards):
    kept, removed = dedupe(cards)
    return [c.front for c in kept], [(c.front, r) for c, r in removed]


def test_same_front_keeps_the_first():
    kept, removed = dedupe([card("Osmosis", "first"), card("osmosis ", "second")])
    assert [c.back for c in kept] == ["first"]
    assert removed[0][1] == "same front as an earlier card"


def test_near_duplicate_with_different_front():
    kept, removed = reasons([
        card("Diffusion", "net movement of particles from high to low concentration"),
        card("Diffusion.", "net movement of particles from high to low concentration."),
    ])  # fmt: skip
    assert kept == ["Diffusion"]
    assert removed == [("Diffusion.", "near-duplicate of an earlier card")]


def test_different_cards_are_kept():
    kept, _ = reasons([
        card("Active transport", "movement against a gradient using ATP"),
        card("Passive transport", "movement down a gradient without energy"),
    ])  # fmt: skip
    assert kept == ["Active transport", "Passive transport"]


def test_bad_cards_are_dropped_with_a_reason():
    _, removed = reasons([
        card("Osmosis", ""),
        card("X", "too short a front"),
        card("Osmosis", "x" * (MAX_BACK_CHARS + 1)),
        card("Same text", "same  TEXT"),
    ])  # fmt: skip
    assert [r for _, r in removed] == ["empty side", "empty side", "too long", "back repeats front"]


def test_cloze_cards_have_no_back():
    kept, removed = dedupe([card("{{c1::Cells}} are the unit of life.", "", kind="cloze")])
    assert len(kept) == 1 and not removed
