from pathlib import Path

from typer.testing import CliRunner

from autoflashcards import __version__
from autoflashcards.cli import app

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
    # 6 term_colon cards; the second "Osmosis" shares an ID with the first
    assert "Wrote 6 cards" in result.output
    assert out.stat().st_size > 0


def test_unsupported_file_type(tmp_path):
    pdf = tmp_path / "notes.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    result = runner.invoke(app, [str(pdf)])
    assert result.exit_code == 2
    assert "unsupported file type" in result.output


def test_no_cards_exits_nonzero(tmp_path):
    empty = tmp_path / "empty.md"
    empty.write_text("# Just a heading\n\nNo definitions here.\n", encoding="utf-8")
    result = runner.invoke(app, [str(empty), "--out", str(tmp_path / "x.apkg")])
    assert result.exit_code == 1
    assert not (tmp_path / "x.apkg").exists()
