from typer.testing import CliRunner

from autoflashcards import __version__
from autoflashcards.cli import app

runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Build an Anki deck" in result.output


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_unbuilt_pipeline_fails_loudly(tmp_path):
    result = runner.invoke(app, [str(tmp_path / "notes.md")])
    assert result.exit_code == 1
