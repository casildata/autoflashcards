"""Command-line entry point: `autoflashcards INPUT...`."""

from pathlib import Path
from typing import Annotated

import typer

from autoflashcards import __version__, readers, rules
from autoflashcards.export import write_apkg

app = typer.Typer(add_completion=False)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"autoflashcards {__version__}")
        raise typer.Exit()


@app.command()
def main(
    inputs: Annotated[
        list[Path],
        typer.Argument(exists=True, dir_okay=False, help="PDF or Markdown files."),
    ],
    out: Annotated[
        Path | None, typer.Option(help="Output .apkg (default: first input's name).")
    ] = None,
    deck: Annotated[
        str | None, typer.Option(help="Deck name (default: first input's name).")
    ] = None,
    version: Annotated[
        bool,
        typer.Option("--version", callback=_print_version, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    """Build an Anki deck from INPUT files."""
    deck_name = deck or inputs[0].stem
    out = out or inputs[0].with_suffix(".apkg")

    blocks = []
    for path in inputs:
        try:
            blocks += readers.read(path)
        except ValueError as err:
            typer.echo(f"Error: {err}", err=True)
            raise typer.Exit(code=2) from err

    cards = rules.generate(blocks)
    if not cards:
        typer.echo("No cards found; nothing written.", err=True)
        raise typer.Exit(code=1)

    count = write_apkg(cards, deck_name, out)
    typer.echo(f"Wrote {count} cards to {out}")
