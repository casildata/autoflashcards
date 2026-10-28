import json
import re
from pathlib import Path

from typer.testing import CliRunner

from autoflashcards import __version__, readers
from autoflashcards.cli import _deck_summary, app
from autoflashcards.models import Card

FIXTURE = Path(__file__).parent / "fixtures" / "cells.md"
runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Build an Anki deck" in result.output


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_markdown_to_apkg(tmp_path):
    out = tmp_path / "deck.apkg"
    result = runner.invoke(app, [str(FIXTURE), "--out", str(out)])
    assert result.exit_code == 0, result.output
    # 7 term_colon, 1 bold_lead, 2 definition_sentence; the second "Osmosis" is dropped
    assert "Wrote 10 cards" in result.output
    assert (
        "Dropped 1 card(s): 1 same front as an earlier card; run with --json to review them"
        in result.output
    )
    assert out.stat().st_size > 0


def test_dropped_summary_points_to_the_json(tmp_path):
    out = tmp_path / "deck.apkg"
    result = runner.invoke(app, [str(FIXTURE), "--out", str(out), "--json"])
    assert result.exit_code == 0, result.output
    assert (
        f"Dropped 1 card(s): 1 same front as an earlier card; listed in {out.with_suffix('.json')}"
        in result.output
    )


def test_pdf_to_apkg(cells_pdf, tmp_path):
    out = tmp_path / "deck.apkg"
    result = runner.invoke(app, [str(cells_pdf), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "Wrote 9 cards" in result.output


def test_summary_says_what_was_made_and_what_to_do_next(cells_pdf, tmp_path):
    out = tmp_path / "deck.apkg"
    result = runner.invoke(app, [str(cells_pdf), "--out", str(out)])
    assert result.exit_code == 0, result.output
    # the deck's size, then its cards per rule, most first
    assert re.search(rf"Wrote 9 cards to {re.escape(str(out))} \(\d+ KB\)\n  \w+ \d", result.output)
    assert re.search(r"Done in \d+\.\d s\. Next: double-click deck\.apkg to import it into Anki "
                     r"\(or File > Import\); once imported, the file can be deleted\.$",
                     result.output.strip())  # fmt: skip
    # progress bars are for terminals only: tests, pipes and CI get none
    assert "Reading cells.pdf" not in result.output


def test_summary_of_a_lone_diagram():
    figure = Card("p.1 figure 1", "Nucleus\nNucleolus", "diagram", "cell.png", kind="diagram")
    out = Path(__file__)  # any existing file, for its size
    assert _deck_summary([figure], out).startswith(
        f"Wrote 1 diagram (2 cards, one per box) to {out} ("
    )


def test_pdf_pages_report_progress(cells_pdf):
    calls = []
    readers.read(cells_pdf, lambda *c: calls.append(c))
    assert calls == [(page, len(calls)) for page in range(1, len(calls) + 1)]


def test_csv_and_json_next_to_the_deck(tmp_path):
    out = tmp_path / "deck.apkg"
    result = runner.invoke(app, [str(FIXTURE), "--out", str(out), "--csv", "--json"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "deck.csv").exists()
    assert (tmp_path / "deck.json").exists()


def test_rule_selection(tmp_path):
    out = tmp_path / "deck.apkg"
    result = runner.invoke(app, [str(FIXTURE), "--out", str(out), "--rules", "bold_lead"])
    assert result.exit_code == 0, result.output
    # Golgi apparatus only: "**Osmosis**: …" has a colon, so it's term_colon's
    assert "Wrote 1 cards" in result.output


def test_unknown_rule(tmp_path):
    result = runner.invoke(app, [str(FIXTURE), "--rules", "term_colon,nope"])
    assert result.exit_code == 2
    assert "unknown rule(s): nope" in result.output


def test_unsupported_file_type(tmp_path):
    doc = tmp_path / "notes.docx"
    doc.write_bytes(b"PK")
    result = runner.invoke(app, [str(doc)])
    assert result.exit_code == 2
    assert "unsupported file type" in result.output


def test_damaged_pdf(tmp_path):
    pdf = tmp_path / "notes.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    result = runner.invoke(app, [str(pdf)])
    assert result.exit_code == 2
    assert "can't read notes.pdf" in result.output


def test_no_cards_exits_nonzero(tmp_path):
    empty = tmp_path / "empty.md"
    empty.write_text("# Just a heading\n\nNo definitions here.\n", encoding="utf-8")
    result = runner.invoke(app, [str(empty), "--out", str(tmp_path / "x.apkg"), "--json"])
    assert result.exit_code == 1
    assert not (tmp_path / "x.apkg").exists()
    assert (tmp_path / "x.json").exists()  # still written, to show what was extracted


def _fake_ai(monkeypatch, tmp_path, ask):
    from autoflashcards import ai

    monkeypatch.setattr(ai, "BACKENDS", {"claude": lambda model: ask, "ollama": ai.ollama})
    monkeypatch.setattr("typer.get_app_dir", lambda name: str(tmp_path / "app"))


def test_ai_cards_are_added_after_rule_cards(monkeypatch, tmp_path):
    from autoflashcards.ai import AICard, AICards

    reply = AICards(cards=[
        AICard(kind="basic", front="Cell theory unit", back="the basic unit of life",
               quote="Cells are the basic unit of life."),
        # same front as a rule card: dropped as a duplicate
        AICard(kind="basic", front="Osmosis", back="movement of water",
               quote="movement of water across a semipermeable membrane"),
    ])  # fmt: skip
    _fake_ai(monkeypatch, tmp_path, lambda text: reply)
    out = tmp_path / "deck.apkg"
    result = runner.invoke(app, [str(FIXTURE), "--out", str(out), "--ai", "claude", "--json"])
    assert result.exit_code == 0, result.output
    assert "sends the text of your files to Anthropic" in result.output  # first run only
    assert "Wrote 11 cards" in result.output
    rules = [c["rule"] for c in json.loads(out.with_suffix(".json").read_text())["cards"]]
    assert rules[-1] == "ai_claude" and rules.count("ai_claude") == 1

    again = runner.invoke(app, [str(FIXTURE), "--out", str(out), "--ai", "claude"])
    assert "sends the text" not in again.output


def test_ai_backend_unavailable_exits_2(monkeypatch, tmp_path):
    from autoflashcards import ai

    def no_key(text):
        raise ai.AIUnavailable("no Anthropic credentials")

    _fake_ai(monkeypatch, tmp_path, no_key)
    result = runner.invoke(app, [str(FIXTURE), "--out", str(tmp_path / "d.apkg"), "--ai", "claude"])
    assert result.exit_code == 2
    assert "no Anthropic credentials" in result.output


def test_unknown_ai_backend(tmp_path):
    result = runner.invoke(app, [str(FIXTURE), "--out", str(tmp_path / "d.apkg"), "--ai", "gpt"])
    assert result.exit_code == 2
    assert "--ai must be one of: claude, claude-code, ollama" in result.output


def test_preview_prints_cards_and_writes_no_deck(tmp_path):
    out = tmp_path / "deck.apkg"
    result = runner.invoke(app, [str(FIXTURE), "--out", str(out), "--preview"])
    assert result.exit_code == 0, result.output
    assert "2. Osmosis\n   movement of water across a semipermeable membrane.\n" in result.output
    assert "(term_colon; cells.md · Cell Biology › Transport)" in result.output
    assert not out.exists()


def test_preview_file(tmp_path):
    out, preview = tmp_path / "deck.apkg", tmp_path / "preview.txt"
    result = runner.invoke(app, [str(FIXTURE), "--out", str(out), "--preview-file", str(preview)])
    assert result.exit_code == 0, result.output
    assert f"Wrote a preview of 10 cards to {preview}; no deck written" in result.output
    assert preview.read_text(encoding="utf-8").startswith("1. {{c1::Cells}} are the basic unit")
    assert not out.exists()


def test_locked_output_file(monkeypatch, tmp_path):
    def locked(cards, deck_name, out):
        raise PermissionError(13, "Permission denied", str(out))

    monkeypatch.setattr("autoflashcards.cli.write_csv", locked)
    out = tmp_path / "deck.apkg"
    result = runner.invoke(app, [str(FIXTURE), "--out", str(out), "--csv"])
    assert result.exit_code == 1
    assert f"Error: can't write {out.with_suffix('.csv')}. If it's open" in result.output
    assert not isinstance(result.exception, PermissionError)  # a message, not a traceback
