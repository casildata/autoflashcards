"""The eval scorer's matching (eval/score.py)."""

from score import matches, score

from autoflashcards.models import Card

GOLD = {"term": "Gene", "fact": "a stretch of DNA that carries the instructions for one protein"}


def basic(front, back):
    return Card(front, back, "term_colon", "x.pdf")


def cloze(text):
    return Card(text, "", "definition_sentence", "x.pdf", kind="cloze")


def test_basic_card_matches_term_and_fact():
    assert matches(basic("Gene", "stretch of DNA carrying instructions for one protein"), GOLD)
    assert matches(basic("Genes (units of heredity)", "a stretch of DNA that carries the "
                         "instructions for one protein"), GOLD)  # fmt: skip


def test_cloze_card_matches_its_hidden_words():
    card = cloze(
        "A {{c1::gene}} is a stretch of DNA that carries the instructions for one protein."
    )
    assert matches(card, GOLD)


def test_right_term_with_the_wrong_fact_does_not_match():
    assert not matches(basic("Gene", "found on chromosomes"), GOLD)
    assert not matches(basic("Genome", GOLD["fact"]), GOLD)


def test_score_counts_hits_duplicates_extras_and_misses():
    gold = [GOLD, {"term": "Allele", "fact": "a version of a gene"}]
    cards = [
        basic("Gene", GOLD["fact"]),
        cloze("A {{c1::gene}} is a stretch of DNA that carries the instructions for one protein."),
        basic("Mendel", "crossed pea plants"),
    ]
    result = score("doc", cards, gold)
    assert (result.hits, result.precision, result.recall) == (1, 1 / 3, 1 / 2)
    assert [c.kind for c in result.duplicates] == ["cloze"]
    assert [c.front for c in result.extra] == ["Mendel"]
    assert [g["term"] for g in result.missed] == ["Allele"]


def test_each_card_claims_its_closest_gold_card():
    gold = [
        {"term": "Biotic Factors", "fact": "living parts of an environment"},
        {"term": "Abiotic Factors", "fact": "nonliving parts of an environment"},
    ]
    cards = [
        basic("Biotic Factors", "Living parts of an environment"),
        basic("Abiotic Factors", "Nonliving parts of an environment"),
    ]
    result = score("doc", cards, gold)
    assert (result.hits, result.found, result.duplicates) == (2, 2, [])


def test_one_cloze_card_can_find_two_gold_cards():
    gold = [
        {"term": "Homozygous", "fact": "having two identical alleles"},
        {"term": "Heterozygous", "fact": "having two different alleles"},
    ]
    card = cloze("{{c1::Homozygous}} means having two identical alleles, and "
                 "{{c2::heterozygous}} means having two different alleles.")  # fmt: skip
    result = score("doc", [card], gold)
    assert (result.hits, result.found, result.precision, result.recall) == (1, 2, 1.0, 1.0)
