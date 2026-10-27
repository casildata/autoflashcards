"""Score the rules against hand-written gold cards and write outputs/eval.md.

    python eval/score.py            # the generated documents in eval/gold
    python eval/score.py --private  # your own PDFs: eval/private/<name>.pdf + <name>.jsonl

A gold line is {"term": ..., "fact": ...}: something a student should get a card for. A card
matches when it asks for that term (a basic card's front, a cloze card's hidden words) and
its answer says the fact. A second card for the same term counts as a duplicate.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from rapidfuzz import fuzz

from autoflashcards import readers, rules
from autoflashcards.dedupe import dedupe
from autoflashcards.export import write_apkg
from autoflashcards.models import Card, normalize

ROOT = Path(__file__).parent.parent
TERM_MATCH = 85  # rapidfuzz ratio between a card's term and the gold term
FACT_MATCH = 70  # token_set_ratio between a card's answer and the gold fact
_CLOZE = re.compile(r"\{\{c\d+::(.+?)\}\}")


def _plain(text: str) -> str:
    text = re.sub(r"\s*\([^)]*\)", "", normalize(text))  # "genes (made of dna)" → "genes"
    return re.sub(r"^(the|a|an)\s+", "", text).strip(" .:")


def asks(card: Card) -> list[tuple[str, str]]:
    """(term, answer) pairs: what the card quizzes and what it says about it. A cloze card
    asks one question per deletion."""
    if card.kind == "basic":
        return [(card.front, card.back)]
    questions = []
    for hidden in _CLOZE.finditer(card.front):
        rest = card.front[: hidden.start()] + card.front[hidden.end() :]
        questions.append((hidden[1], _CLOZE.sub(r"\1", rest)))
    return questions


def _closeness(question: tuple[str, str], gold: dict) -> float:
    """How well a question's term matches the gold term, or 0 if it isn't a match."""
    term, answer = question
    closeness = fuzz.ratio(_plain(term), _plain(gold["term"]))
    fact = fuzz.token_set_ratio(normalize(answer), normalize(gold["fact"]))
    return closeness if closeness >= TERM_MATCH and fact >= FACT_MATCH else 0


def matches(card: Card, gold: dict) -> bool:
    return any(_closeness(question, gold) for question in asks(card))


@dataclass
class Score:
    name: str
    cards: int = 0
    gold: int = 0
    hits: int = 0  # cards that match a gold card not matched before
    found: int = 0  # gold cards matched (one cloze card can match several)
    duplicates: list[Card] = field(default_factory=list)
    extra: list[Card] = field(default_factory=list)  # cards that match no gold card
    missed: list[dict] = field(default_factory=list)

    @property
    def precision(self) -> float:
        return self.hits / self.cards if self.cards else 0.0

    @property
    def recall(self) -> float:
        return self.found / self.gold if self.gold else 0.0


def score(name: str, cards: list[Card], gold: list[dict]) -> Score:
    result = Score(name, len(cards), len(gold))
    found = [False] * len(gold)
    for card in cards:
        # each question claims its closest unmatched gold card ("Biotic" over "Abiotic")
        new = False
        for question in asks(card):
            closeness = [0 if found[i] else _closeness(question, g) for i, g in enumerate(gold)]
            if max(closeness, default=0):
                found[closeness.index(max(closeness))] = new = True
        if new:
            result.hits += 1
        elif any(matches(card, g) for g in gold):
            result.duplicates.append(card)
        else:
            result.extra.append(card)
    result.found = sum(found)
    result.missed = [g for g, f in zip(gold, found, strict=True) if not f]
    return result


def _card_text(card: Card) -> str:
    if card.kind == "cloze":
        return f"`{card.rule}` {card.front}"
    back = card.back.replace("\n", " / ")
    return f"`{card.rule}` {card.front} → {back}"


def report(scores: list[Score], title: str) -> str:
    total = Score("**All**")
    for s in scores:
        total.cards += s.cards
        total.gold += s.gold
        total.hits += s.hits
        total.found += s.found
        total.duplicates += s.duplicates
    lines = [
        f"# {title}",
        "",
        "| Document | Cards | Gold | Matched | Precision | Recall | Duplicates |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for s in [*scores, total]:
        lines.append(
            f"| {s.name} | {s.cards} | {s.gold} | {s.found} | {s.precision:.0%} "
            f"| {s.recall:.0%} | {len(s.duplicates)} |"
        )
    for s in scores:
        lines += ["", f"## {s.name}"]
        if s.missed:
            lines += ["", "Missed:", *(f"- {g['term']} → {g['fact']}" for g in s.missed)]
        if s.extra or s.duplicates:
            lines += ["", "Not in the gold set:", *(f"- {_card_text(c)}" for c in s.extra)]
            lines += [f"- (duplicate) {_card_text(c)}" for c in s.duplicates]
        if not (s.missed or s.extra or s.duplicates):
            lines += ["", "All gold cards found, nothing extra."]
    return "\n".join(lines) + "\n"


def run(documents: dict[str, Path], gold_dir: Path, out_dir: Path) -> list[Score]:
    """Score each document against gold_dir/<name>.jsonl and write its deck to out_dir."""
    scores = []
    for name, path in documents.items():
        gold_lines = (gold_dir / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
        gold = [json.loads(line) for line in gold_lines if line.strip()]
        cards, _ = dedupe(rules.generate(readers.read(path)))
        if cards:
            write_apkg(cards, name, out_dir / f"{name}.apkg")
        scores.append(score(name, cards, gold))
    return scores


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--private", action="store_true", help="score eval/private/ instead")
    args = parser.parse_args()

    if args.private:
        gold_dir = out_dir = ROOT / "eval" / "private"
        documents = {p.stem: p for p in sorted(gold_dir.glob("*.pdf"))}
        title, report_path = "Evaluation (private documents)", gold_dir / "eval.md"
    else:
        sys.path.insert(0, str(Path(__file__).parent))
        from make_docs import build_all

        gold_dir, out_dir = ROOT / "eval" / "gold", ROOT / "outputs" / "eval"
        documents = build_all(out_dir)
        title, report_path = "Evaluation", ROOT / "outputs" / "eval.md"

    if not documents:
        print(f"No PDFs in {gold_dir}", file=sys.stderr)
        return 1
    scores = run(documents, gold_dir, out_dir)
    text = report(scores, title)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")
    print(text)
    # a crash or no cards at all fails CI; low scores are reported, not failed
    return 0 if sum(s.cards for s in scores) else 1


if __name__ == "__main__":
    sys.exit(main())
