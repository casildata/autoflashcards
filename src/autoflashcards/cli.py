"""Command-line entry point: `autoflashcards INPUT...`."""

from collections import Counter
from pathlib import Path
from typing import Annotated

import typer

from autoflashcards import __version__, readers, rules
from autoflashcards.dedupe import dedupe
from autoflashcards.export import write_apkg, write_csv, write_json
from autoflashcards.models import Block, Card

app = typer.Typer(add_completion=False)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"autoflashcards {__version__}")
        raise typer.Exit()


def _ai_cards(blocks: list[Block], backend: str, model: str | None) -> list[Card]:
    # imported here: the AI stage needs the optional [ai] extra
    from autoflashcards import ai

    if backend not in ai.BACKENDS:
        typer.echo(f"Error: --ai must be one of: {', '.join(ai.BACKENDS)}", err=True)
        raise typer.Exit(code=2)
    model = model or ai.MODELS[backend]
    app_dir = Path(typer.get_app_dir("autoflashcards"))
    notice = app_dir / "claude-notice-shown"
    if backend.startswith("claude") and not notice.exists():
        typer.echo(
            f"Note: --ai {backend} sends the text of your files to Anthropic. "
            "Use --ai ollama to keep everything on this computer. (Shown once.)",
            err=True,
        )
        notice.parent.mkdir(parents=True, exist_ok=True)
        notice.touch()

    texts = [ai.render(chunk) for chunk in ai.chunks(blocks)]
    typer.echo(
        f"AI: {len(texts)} request(s) to {model}, about {ai.estimate_tokens(texts):,} input "
        "tokens (cached replies are reused)",
        err=True,
    )
    try:
        return ai.generate(
            blocks,
            backend,
            model,
            ai.BACKENDS[backend](model),
            cache_dir=app_dir / "cache",
            warn=lambda message: typer.echo(message, err=True),
        )
    except ai.AIUnavailable as err:
        typer.echo(f"Error: {err}", err=True)
        raise typer.Exit(code=2) from err


def _dropped_summary(removed: list[tuple[Card, str]], json_path: Path | None) -> str:
    counts = Counter(reason for _, reason in removed)
    reasons = ", ".join(f"{n} {reason}" for reason, n in counts.most_common())
    where = f"listed in {json_path}" if json_path else "run with --json to review them"
    return f"Dropped {len(removed)} card(s): {reasons}; {where}"


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
    ai: Annotated[
        str | None,
        typer.Option(
            "--ai",
            help="Also make cards with a model: claude (Anthropic API key), claude-code "
            "(your Claude Pro/Max plan, through Claude Code) or ollama (local).",
        ),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option(help="Model for --ai (default: claude-haiku-5-5, or llama3.2 for ollama)."),
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

    cards = rules.generate(blocks, selected)
    if ai:
        cards += _ai_cards(blocks, ai, model)
    cards, removed = dedupe(cards)  # rule cards come first, so they win over AI duplicates
    if json:  # written even when there are no cards: that's when it's most useful
        write_json(blocks, cards, removed, out.with_suffix(".json"))
        typer.echo(f"Wrote {len(blocks)} blocks to {out.with_suffix('.json')}")
    if removed:
        typer.echo(_dropped_summary(removed, out.with_suffix(".json") if json else None))
    if not cards:
        typer.echo("No cards found; no deck written.", err=True)
        raise typer.Exit(code=1)

    write_apkg(cards, deck_name, out)
    typer.echo(f"Wrote {len(cards)} cards to {out}")
    if csv:
        write_csv(cards, deck_name, out.with_suffix(".csv"))
        typer.echo(f"Wrote {len(cards)} cards to {out.with_suffix('.csv')}")
