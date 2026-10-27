"""Command-line entry point: `autoflashcards INPUT...`."""

from pathlib import Path
from typing import Annotated

import typer

from autoflashcards import __version__

app = typer.Typer(add_completion=False)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"autoflashcards {__version__}")
        raise typer.Exit()


@app.command()
def main(
    inputs: Annotated[list[Path], typer.Argument(help="PDF, PPTX or Markdown files.")],
    version: Annotated[
        bool,
        typer.Option("--version", callback=_print_version, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    """Build an Anki deck from INPUT files."""
    typer.echo("The card pipeline isn't built yet.", err=True)
    raise typer.Exit(code=1)
