"""Filter stage: drop cards that are too long, empty, or duplicates of an earlier card."""

from rapidfuzz import fuzz

from autoflashcards.models import Card, normalize

MAX_FRONT_CHARS = 200
MAX_BACK_CHARS = 600
MAX_CLOZE_CHARS = 600
NEAR_DUPLICATE = 90  # rapidfuzz ratio (0-100) of front + back at or above which cards match


def _problem(card: Card) -> str | None:
    if card.kind == "diagram":  # its "back" is the list of labels, as long as the figure needs
        return None
    if card.kind == "cloze":
        return "too long" if len(card.front) > MAX_CLOZE_CHARS else None
    if len(card.front) < 2 or not card.back:
        return "empty side"
    if len(card.front) > MAX_FRONT_CHARS or len(card.back) > MAX_BACK_CHARS:
        return "too long"
    if normalize(card.back) == normalize(card.front):
        return "back repeats front"
    return None


def dedupe(cards: list[Card]) -> tuple[list[Card], list[tuple[Card, str]]]:
    """Keep the first of each group of duplicates. Returns (kept, [(removed, reason)])."""
    kept: list[Card] = []
    removed: list[tuple[Card, str]] = []
    fronts: set[str] = set()
    texts: list[str] = []
    for card in cards:
        if reason := _problem(card):
            removed.append((card, reason))
            continue
        front = normalize(card.front)
        text = normalize(f"{card.front} {card.back}")
        if front in fronts:  # also required by Anki: the front is the note ID
            removed.append((card, "same front as an earlier card"))
            continue
        # diagram cards differ in their images, which the text doesn't show
        near = card.kind != "diagram" and any(
            fuzz.ratio(text, t, score_cutoff=NEAR_DUPLICATE) for t in texts
        )
        if near:
            removed.append((card, "near-duplicate of an earlier card"))
            continue
        fronts.add(front)
        texts.append(text)
        kept.append(card)
    return kept, removed
