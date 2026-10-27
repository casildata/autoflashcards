"""Generate test PDFs with known layout. Run directly to write them to tests/fixtures/ for a look.

The text is original, so no third-party documents are committed.
"""

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

BODY, REGULAR, BOLD = 10.5, "Helvetica", "Helvetica-Bold"
WIDTH, HEIGHT = letter
LEFT, TOP = 72, HEIGHT - 72

# (kind, text) per page. Kinds: title (20pt), h1 (14pt bold), h2 (body size, bold),
# para (body), bullet ("•" + indented text), term (bold term, regular definition), gap
PAGES = [
    [
        ("title", "Cell Biology"),
        ("para", "Cells are the basic unit of life. Every living thing is made of one or"),
        ("para", "more cells, and new cells come only from existing cells."),
        ("gap", ""),
        ("h1", "Transport"),
        ("term", "Osmosis: movement of water across a semipermeable membrane."),
        ("bullet", "Diffusion: net movement of particles from high to low"),
        ("cont", "concentration, without energy input."),
        ("bullet", "Active transport: movement against a gradient that uses ATP."),
    ],
    [
        ("h2", "Membrane Proteins"),
        ("para", "1. Channel protein: forms a pore that lets specific ions pass."),
        ("para", "2. Carrier protein: changes shape to move a molecule across the mem-"),
        ("para", "brane."),
    ],
    [
        ("h1", "Organelles"),
        ("para", "Mitochondrion: the site of aerobic respiration."),
        ("para", "Ribosome: assembles proteins from amino acids."),
    ],
]


def build_cells_pdf(path: Path) -> Path:
    canvas = Canvas(str(path), pagesize=letter)
    for number, lines in enumerate(PAGES, start=1):
        # running header and footer, repeated on every page
        canvas.setFont(REGULAR, 9)
        canvas.drawString(LEFT, HEIGHT - 40, "BIO 101 - Lecture 3")
        canvas.drawString(WIDTH / 2, 30, f"Page {number} of {len(PAGES)}")

        y = TOP
        for kind, text in lines:
            if kind == "title":
                canvas.setFont(BOLD, 20)
                canvas.drawString(LEFT, y, text)
                y -= 32
            elif kind == "h1":
                y -= 8
                canvas.setFont(BOLD, 14)
                canvas.drawString(LEFT, y, text)
                y -= 22
            elif kind == "h2":
                canvas.setFont(BOLD, BODY)
                canvas.drawString(LEFT, y, text)
                y -= 18
            elif kind == "gap":
                y -= 10
            elif kind == "term":
                term, definition = text.split(":", 1)
                canvas.setFont(BOLD, BODY)
                canvas.drawString(LEFT, y, term + ":")
                canvas.setFont(REGULAR, BODY)
                canvas.drawString(LEFT + canvas.stringWidth(term + ": ", BOLD, BODY), y, definition)
                y -= 15
            else:
                canvas.setFont(REGULAR, BODY)
                if kind == "bullet":
                    canvas.drawString(LEFT, y, "•")
                x = LEFT + 14 if kind in ("bullet", "cont") else LEFT
                canvas.drawString(x, y, text)
                y -= 15
        canvas.showPage()
    canvas.save()
    return path


LEFT_COLUMN = [
    "Enzyme: a protein that speeds up a",
    "chemical reaction.",
    "Substrate: the molecule an enzyme",
    "acts on.",
]
RIGHT_COLUMN = [
    "Active site: the region where the",
    "substrate binds.",
    "Inhibitor: a molecule that slows an",
    "enzyme down.",
]


def build_two_column_pdf(path: Path) -> Path:
    """One page: a full-width title, then two columns read left first."""
    canvas = Canvas(str(path), pagesize=letter)
    canvas.setFont(BOLD, 20)
    canvas.drawString(LEFT, TOP, "Enzymes")
    canvas.setFont(REGULAR, BODY)
    right_x = WIDTH / 2 + 18
    for i, (left_text, right_text) in enumerate(zip(LEFT_COLUMN, RIGHT_COLUMN, strict=True)):
        y = TOP - 36 - i * 15
        canvas.drawString(LEFT, y, left_text)
        canvas.drawString(right_x, y, right_text)
    canvas.showPage()
    canvas.save()
    return path


if __name__ == "__main__":
    out = Path(__file__).parent / "fixtures"
    print(build_cells_pdf(out / "cells.pdf"))
    print(build_two_column_pdf(out / "two_column.pdf"))
