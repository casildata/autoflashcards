"""Command-line entry point: `autoflashcards INPUT...`."""

from pathlib import Path
from typing import Annotated

import typer

from autoflashcards import __version__, readers, rules
from autoflashcards.dedupe import dedupe
from autoflashcards.export import write_apkg, write_csv, write_json

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
    csv: Annotated[
        bool, typer.Option("--csv", help="Also write a .csv for Anki's text import.")
    ] = False,
    json: Annotated[
        bool,
        typer.Option("--json", help="Also write a .json of extracted blocks, cards and drops."),
    ] = False,
    rule_names: Annotated[
        str | None,
        typer.Option(
            "--rules",
            help=f"Comma-separated rules to use (default: all): {', '.join(rules.RULES)}.",
        ),
    ] = None,
    version: Annotated[
        bool,
        typer.Option("--version", callback=_print_version, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    """Build an Anki deck from INPUT files."""
    deck_name = deck or inputs[0].stem
    out = out or inputs[0].with_suffix(".apkg")

    selected = None
    if rule_names:
        selected = [name.strip() for name in rule_names.split(",") if name.strip()]
        unknown = [name for name in selected if name not in rules.RULES]
        if unknown:
            typer.echo(f"Error: unknown rule(s): {', '.join(unknown)}", err=True)
            raise typer.Exit(code=2)

    blocks = []
    for path in inputs:
        try:
            blocks += readers.read(path)
        except ValueError as err:
            typer.echo(f"Error: {err}", err=True)
            raise typer.Exit(code=2) from err

    cards, removed = dedupe(rules.generate(blocks, selected))
    if json:  # written even when there are no cards: that's when it's most useful
        write_json(blocks, cards, removed, out.with_suffix(".json"))
        typer.echo(f"Wrote {len(blocks)} blocks to {out.with_suffix('.json')}")
    if not cards:
        typer.echo("No cards found; no deck written.", err=True)
        raise typer.Exit(code=1)

    write_apkg(cards, deck_name, out)
    dropped = f" ({len(removed)} dropped as duplicates or too long)" if removed else ""
    typer.echo(f"Wrote {len(cards)} cards to {out}{dropped}")
    if csv:
        write_csv(cards, deck_name, out.with_suffix(".csv"))
        typer.echo(f"Wrote {len(cards)} cards to {out.with_suffix('.csv')}")
