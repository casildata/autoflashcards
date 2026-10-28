"""Command-line entry point: `autoflashcards INPUT...`."""

import sys
import time
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
)

from autoflashcards import __version__, diagrams, readers, rules
from autoflashcards.dedupe import dedupe
from autoflashcards.export import (
    SIO_NOTETYPE,
    preview_text,
    write_apkg,
    write_csv,
    write_json,
    write_media,
    write_sio_csv,
)
from autoflashcards.models import Block, Card

app = typer.Typer(add_completion=False)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"autoflashcards {__version__}")
        raise typer.Exit()


Step = Callable[[int, int], None]  # progress(done, total)


@contextmanager
def _progress() -> Iterator[Callable[[str, str], Step | None]]:
    """Yields `step(description, unit)`, which adds a progress bar for one slow step (a PDF's
    pages, diagram OCR, AI requests) and returns its callback. Bars go to stderr, so stdout
    stays clean for --preview, and only to a terminal: pipes, CI and tests get none."""
    console = Console(stderr=True)
    if not console.is_terminal:
        yield lambda description, unit: None
        return
    columns = (
        TextColumn("{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("{task.fields[unit]}"),
        TimeRemainingColumn(elapsed_when_finished=True),
    )
    with Progress(*columns, console=console) as bars:  # warnings print above the bars

        def step(description: str, unit: str) -> Step:
            task = bars.add_task(description, total=None, unit=unit)
            return lambda done, total: bars.update(task, completed=done, total=total)

        yield step


def _ai_cards(
    blocks: list[Block], backend: str, model: str | None, progress: Step | None
) -> list[Card]:
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
            progress=progress,
        )
    except ai.AIUnavailable as err:
        typer.echo(f"Error: {err}", err=True)
        raise typer.Exit(code=2) from err


def _dropped_summary(removed: list[tuple[Card, str]], json_path: Path | None) -> str:
    counts = Counter(reason for _, reason in removed)
    reasons = ", ".join(f"{n} {reason}" for reason, n in counts.most_common())
    where = f"listed in {json_path}" if json_path else "run with --json to review them"
    return f"Dropped {len(removed)} card(s): {reasons}; {where}"


def _size(path: Path) -> str:
    size = path.stat().st_size
    return f"{size / 1e6:.1f} MB" if size >= 1e6 else f"{max(size / 1e3, 1):.0f} KB"


def _deck_summary(cards: list[Card], out: Path) -> str:
    """What the .apkg holds: cards, diagram notes and their boxes, and cards per rule."""
    text_cards = [c for c in cards if c.kind != "diagram"]
    figures = [c for c in cards if c.kind == "diagram"]
    parts = [f"{len(text_cards)} cards"] if text_cards else []
    if figures:
        boxes = sum(len(c.back.splitlines()) for c in figures)
        diagram_s = "diagram" if len(figures) == 1 else "diagrams"
        parts.append(f"{len(figures)} {diagram_s} ({boxes} cards, one per box)")
    what = " and ".join(parts)
    rules_used = Counter(c.rule for c in text_cards).most_common()
    by_rule = ", ".join(f"{rule} {n}" for rule, n in rules_used)  # ASCII: stdout may be cp1252
    return f"Wrote {what} to {out} ({_size(out)})" + (f"\n  {by_rule}" if by_rule else "")


@contextmanager
def _writing(path: Path) -> Iterator[None]:
    # Windows won't let anyone write to a file that Excel has open
    try:
        yield
    except PermissionError as err:
        typer.echo(
            f"Error: can't write {path}. If it's open in another program (Excel, for example), "
            "close it and run again.",
            err=True,
        )
        raise typer.Exit(code=1) from err


@app.command()
def main(
    inputs: Annotated[
        list[Path],
        typer.Argument(
            exists=True,
            dir_okay=False,
            help="PDF or Markdown files, or diagram pictures (PNG, JPEG; need Tesseract).",
        ),
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
    preview: Annotated[
        bool, typer.Option("--preview", help="Print the cards instead of writing a deck.")
    ] = False,
    preview_file: Annotated[
        Path | None, typer.Option(help="Like --preview, but save the list to this file.")
    ] = None,
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
    with_diagrams: Annotated[
        bool,
        typer.Option(
            "--diagrams",
            help="Also make Anki Image Occlusion notes from labeled diagrams in PDFs: one note "
            "per diagram, a box over every label, one card per box.",
        ),
    ] = False,
    type_answers: Annotated[
        bool,
        typer.Option(
            "--type-answers",
            help="Diagram notes: each card also has a box to type the label of its box, "
            "checked against the note's Image Labels field.",
        ),
    ] = False,
    sio: Annotated[
        bool,
        typer.Option(
            "--sio",
            help=f"Diagram notes for the Simple Image Occlusion add-on instead: written to "
            f"OUT-sio.csv for its '{SIO_NOTETYPE}' note type, not to the .apkg, with their "
            "images in --media-dir. Its editor adds and removes boxes and edits their labels.",
        ),
    ] = False,
    media_dir: Annotated[
        Path | None,
        typer.Option(
            help="With --sio: folder for the images (default: OUT-media). Give Anki's "
            "collection.media folder to skip copying them there yourself."
        ),
    ] = None,
    link_pdf: Annotated[
        bool,
        typer.Option(
            "--link-pdf",
            help="With --sio: make each diagram note's header a link to its page in the "
            "PDF. The link holds the PDF's full path on this computer.",
        ),
    ] = False,
    version: Annotated[
        bool,
        typer.Option("--version", callback=_print_version, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    """Build an Anki deck from INPUT files."""
    deck_name = deck or inputs[0].stem
    out = out or inputs[0].with_suffix(".apkg")

    if link_pdf and not sio:
        typer.echo(
            "Error: --link-pdf needs --sio (the link is a field of that note type)", err=True
        )
        raise typer.Exit(code=2)

    selected = None
    if rule_names:
        selected = [name.strip() for name in rule_names.split(",") if name.strip()]
        unknown = [name for name in selected if name not in rules.RULES]
        if unknown:
            typer.echo(f"Error: unknown rule(s): {', '.join(unknown)}", err=True)
            raise typer.Exit(code=2)

    start = time.perf_counter()
    blocks = []
    found: list[diagrams.Diagram] = []
    with _progress() as step:
        for path in inputs:
            try:
                if path.suffix.lower() in diagrams.IMAGE_SUFFIXES:
                    found += diagrams.read_image(path)
                    continue
                blocks += readers.read(path, step(f"Reading {path.name}", "pages"))
                if with_diagrams and path.suffix.lower() == ".pdf":
                    found += diagrams.read_pdf(
                        path,
                        warn=lambda m: typer.echo(m, err=True),
                        progress=step(f"Finding diagrams in {path.name}", "pages"),
                    )
            except ValueError as err:
                typer.echo(f"Error: {err}", err=True)
                raise typer.Exit(code=2) from err

        cards = rules.generate(blocks, selected)
        if ai:
            cards += _ai_cards(blocks, ai, model, step(f"AI cards ({ai})", "requests"))
    diagram_cards, media = diagrams.cards(found, typed=type_answers)
    cards += diagram_cards
    cards, removed = dedupe(cards)  # rule cards come first, so they win over AI duplicates
    if json:  # written even when there are no cards: that's when it's most useful
        with _writing(out.with_suffix(".json")):
            write_json(blocks, cards, removed, out.with_suffix(".json"))
        typer.echo(f"Wrote {len(blocks)} blocks to {out.with_suffix('.json')}")
    dropped = _dropped_summary(removed, out.with_suffix(".json") if json else None)
    if not cards:
        if removed:
            typer.echo(dropped)
        typer.echo("No cards found; no deck written.", err=True)
        raise typer.Exit(code=1)

    if preview or preview_file:
        if removed:
            typer.echo(dropped)
    if preview_file:
        with _writing(preview_file):
            preview_file.write_text(preview_text(cards), encoding="utf-8")
        typer.echo(f"Wrote a preview of {len(cards)} cards to {preview_file}; no deck written")
        return
    if preview:
        # source lines have "·" and "›"; Windows pipes and redirects default to cp1252
        sys.stdout.reconfigure(encoding="utf-8")
        typer.echo(preview_text(cards), nl=False)
        return

    sio_cards = [c for c in cards if c.kind == "diagram"] if sio else []
    apkg_cards = [c for c in cards if c not in sio_cards]
    if apkg_cards:
        with _writing(out):
            write_apkg(apkg_cards, deck_name, out, media)
        typer.secho(_deck_summary(apkg_cards, out), fg="green")
    if sio_cards:
        sio_csv = out.with_name(f"{out.stem}-sio.csv")
        media_dir = media_dir or out.with_name(f"{out.stem}-media")
        pdfs = None
        if link_pdf:
            pdfs = {p.name: p for p in inputs if p.suffix.lower() == ".pdf"}
            typer.echo(
                "Warning: --link-pdf puts each PDF's full path in the notes "
                f"({', '.join(str(p.resolve()) for p in pdfs.values())}). The links open only "
                "on this computer, and only while the PDF stays at that path (moving or "
                "renaming it breaks them; run again and re-import to fix them). Anki on a "
                "phone can't open them. Whether the PDF opens at the figure's page depends on "
                "your PDF viewer; some open it at page 1. Anyone you share these notes with "
                "sees the path, which can include your user name and folder names.",
                err=True,
            )
        with _writing(sio_csv):
            write_sio_csv(sio_cards, deck_name, sio_csv, pdfs)
        images = write_media(sio_cards, media, media_dir)
        typer.echo(
            f"Wrote {len(sio_cards)} diagram notes to {sio_csv} and {images} images to "
            f"{media_dir}. In Anki, the images must be in your profile's collection.media "
            f"folder; then File > Import {sio_csv.name} (needs the '{SIO_NOTETYPE}' note "
            "type from the Simple Image Occlusion add-on)."
        )
    if csv:
        with _writing(out.with_suffix(".csv")):
            write_csv(cards, deck_name, out.with_suffix(".csv"))
        text_cards = [c for c in cards if c.kind != "diagram"]
        skipped = len(cards) - len(text_cards)
        note = f" ({skipped} diagram card(s) are in the .apkg only)" if skipped and not sio else ""
        typer.echo(f"Wrote {len(text_cards)} cards to {out.with_suffix('.csv')}{note}")
    if removed:
        typer.echo(dropped)
    done = f"Done in {time.perf_counter() - start:.1f} s."
    if apkg_cards:
        done += (
            f" Next: double-click {out.name} to import it into Anki (or File > Import);"
            " once imported, the file can be deleted."
        )
        if any(c.kind == "diagram" for c in apkg_cards):
            done += " Diagram notes need Anki 23.10 or newer."
    typer.secho(done, bold=True)
