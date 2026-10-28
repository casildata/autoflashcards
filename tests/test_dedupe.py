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


def test_same_front_keeps_the_better_back():
    # from a real run: a passing mention, then the full definition under a later heading
    kept, removed = dedupe([
        card("Osmosis", "movement of water"),
        card("Osmosis", "is the movement of water across a membrane."),
    ])  # fmt: skip
    assert [c.back for c in kept] == ["is the movement of water across a membrane."]
    assert [(c.back, r) for c, r in removed] == [
        ("movement of water", "same front as a later, better card")
    ]


def test_an_ai_card_never_replaces_a_rule_card():
    rule_card = card("Osmosis", "movement of water")
    ai_card = Card("Osmosis", "the movement of water across a membrane.", "ai_claude", "x.md")
    kept, removed = dedupe([rule_card, ai_card])
    assert kept == [rule_card]
    assert removed == [(ai_card, "same front as an earlier card")]


def test_a_back_cut_after_a_linking_word_loses():
    kept, _ = dedupe([
        card("Osmosis", "is water moving across a membrane."),
        card("Osmosis", "water moving across a membrane."),
    ])  # fmt: skip
    assert [c.back for c in kept] == ["water moving across a membrane."]


def test_a_run_on_back_loses_to_a_clean_one():
    run_on = (
        "the movement of water across a membrane. Diffusion is the movement of particles from "
        "high to low concentration, and active transport moves them the other way using ATP "
        "from the mitochondria, which is why cells with a lot of active transport need many "
        "of them and"
    )
    clean = "the movement of water across a membrane."
    kept, _ = dedupe([card("Osmosis", run_on), card("Osmosis", clean)])
    assert [c.back for c in kept] == [clean]


def test_the_better_card_takes_the_first_ones_place():
    kept, _ = reasons([
        card("Osmosis", "movement of water"),
        card("Diffusion", "the movement of particles from high to low concentration."),
        card("Osmosis", "the movement of water across a membrane."),
    ])  # fmt: skip
    assert kept == ["Osmosis", "Diffusion"]


def test_near_duplicate_keeps_the_better_back():
    kept, removed = reasons([
        card("Diffusion", "is net movement of particles from high to low concentration"),
        card("Diffusion.", "net movement of particles from high to low concentration."),
    ])  # fmt: skip
    assert kept == ["Diffusion."]
    assert removed == [("Diffusion", "near-duplicate of a later, better card")]


def test_near_duplicate_with_different_front():
    kept, removed = reasons([
        card("Diffusion", "net movement of particles from high to low concentration"),
        card("Diffusion.", "Net movement of particles from high to low concentration"),
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
