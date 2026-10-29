"""Filter stage: drop cards that are too long, empty, or duplicates of a better card."""

import re

from rapidfuzz import fuzz

from autoflashcards.models import Card, normalize

MAX_FRONT_CHARS = 200
MAX_BACK_CHARS = 600
MAX_CLOZE_CHARS = 600
NEAR_DUPLICATE = 90  # rapidfuzz ratio (0-100) of front + back at or above which cards match
LINKING_WORD = re.compile(r"(is|are|means|refers to)\b")  # a back cut just after the term
# "covered in section 4.3": points to the definition instead of giving it
CROSS_REFERENCE = re.compile(
    r"(see|covered|discussed|described|explained)\b|.*\b(section|chapter)\s+\d"
)


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


def _score(card: Card) -> int:
    """How much a basic card's back looks like a full definition rather than a passing mention."""
    back = normalize(card.back)
    words = back.split()
    score = 0
    if LINKING_WORD.match(back):
        score -= 2
    if CROSS_REFERENCE.match(back):
        score -= 2
    if 4 <= len(words) <= 30:  # shorter is a label, longer ran into the next sentence
        score += 2
    if card.back.rstrip().endswith((".", "!", "?")):
        score += 1
    if set(words) - set(normalize(card.front).split()):
        score += 1
    return score


def _better(card: Card, old: Card) -> bool:
    """Whether `card` should replace the earlier duplicate `old`: a higher score, or the same
    score and a longer back; on a full tie the first one stays."""
    if not card.kind == old.kind == "basic":
        return False
    if card.rule.startswith("ai_") and not old.rule.startswith("ai_"):
        return False  # rule cards come first and win over AI duplicates
    return (_score(card), len(card.back.split())) > (_score(old), len(old.back.split()))


def dedupe(cards: list[Card]) -> tuple[list[Card], list[tuple[Card, str]]]:
    """Keep the best of each group of duplicates. Returns (kept, [(removed, reason)])."""
    kept: list[Card] = []
    removed: list[tuple[Card, str]] = []
    fronts: dict[str, int] = {}  # normalized front -> its card's index in `kept`
    texts: list[str] = []  # front + back of each kept card
    for card in cards:
        if reason := _problem(card):
            removed.append((card, reason))
            continue
        front = normalize(card.front)
        text = normalize(f"{card.front} {card.back}")
        i, match = fronts.get(front), "same front as"  # the front is also Anki's note ID
        # diagram cards differ in their images, which the text doesn't show
        if i is None and card.kind != "diagram":
            near = (
                j for j, t in enumerate(texts) if fuzz.ratio(text, t, score_cutoff=NEAR_DUPLICATE)
            )
            i, match = next(near, None), "near-duplicate of"
        if i is None:
            fronts[front] = len(kept)
            texts.append(text)
            kept.append(card)
        elif _better(card, kept[i]):  # it takes the earlier card's place, so the order stays
            removed.append((kept[i], f"{match} a later, better card"))
            del fronts[normalize(kept[i].front)]
            fronts[front] = i
            texts[i] = text
            kept[i] = card
        else:
            removed.append((card, f"{match} an earlier card"))
    return kept, removed
