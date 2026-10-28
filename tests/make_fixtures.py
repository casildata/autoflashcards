"""Generate test PDFs with known layout. Run directly to write them to tests/fixtures/ for a look.

The text is original, so no third-party documents are committed.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

BODY, REGULAR, BOLD = 10.5, "Helvetica", "Helvetica-Bold"
WIDTH, HEIGHT = letter
LEFT, TOP = 72, HEIGHT - 72

# (kind, text) per page. Kinds: title (20pt), h1 (14pt bold), h2 (body size, bold),
# para (body), bullet ("•" + indented text), term (bold term, regular definition),
# lead (bold text before "|", regular after), gap
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
        ("lead", "Lysosome|breaks down waste inside the cell."),
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
            elif kind in ("term", "lead"):
                if kind == "term":
                    term, definition = text.split(":", 1)
                    term += ":"
                else:
                    term, definition = text.split("|")
                canvas.setFont(BOLD, BODY)
                canvas.drawString(LEFT, y, term)
                canvas.setFont(REGULAR, BODY)
                x = LEFT + canvas.stringWidth(term + " ", BOLD, BODY)
                canvas.drawString(x, y, definition.strip())
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


# A lecture deck exported to PDF: one list per slide. Kinds: divider (40pt section slide),
# title (28pt bold), bullet (18pt), bold_bullet (18pt bold), sub (16pt, indented), caption
SLIDES = [
    [("divider", "43.1"), ("divider", "Innate Immunity")],
    [
        ("title", "Phagocytes"),
        ("bullet", "White blood cells that engulf pathogens"),
        ("bullet", "Include neutrophils and macrophages"),
        ("bullet", "Found in blood and in body tissues"),
        ("bullet", "Part of the first response to infection"),
    ],
    [
        ("title", "Phagocyte Types"),
        ("bold_bullet", "Macrophages"),
        ("sub", "Large phagocytes that live in tissues"),
        ("sub", "Present antigens to T cells"),
        ("bold_bullet", "Neutrophils"),
        ("sub", "Most abundant white blood cells"),
    ],
    [
        ("title", "Chemical Signals"),
        # "->", not "→": the built-in Helvetica can't encode the arrow (rules tests cover it)
        ("bullet", "Cytokines -> signal molecules that recruit immune cells"),
        ("bullet", "Interferons = proteins that interfere with viral replication"),
    ],
    [("title", "Image of a macrophage engulfing bacteria"), ("caption", "Macrophage at work")],
    [("title", "Thanks!"), ("bullet", "Template credits: made with a free slide template")],
]


def build_slides_pdf(path: Path) -> Path:
    width, height = landscape(letter)
    canvas = Canvas(str(path), pagesize=(width, height))
    for slide in SLIDES:
        y = height - 80
        for kind, text in slide:
            if kind == "divider":
                canvas.setFont(BOLD, 40)
                canvas.drawString(LEFT, y, text)
                y -= 60
            elif kind == "title":
                canvas.setFont(BOLD, 28)
                canvas.drawString(LEFT, y, text)
                y -= 50
            elif kind == "caption":
                canvas.setFont(REGULAR, 14)
                canvas.drawString(LEFT, y, text)
                y -= 24
            else:
                bold = kind == "bold_bullet"
                size = 16 if kind == "sub" else 18
                x = LEFT + 30 if kind == "sub" else LEFT
                canvas.setFont(REGULAR, size)
                canvas.drawString(x, y, "–" if kind == "sub" else "•")
                canvas.setFont(BOLD if bold else REGULAR, size)
                canvas.drawString(x + 20, y, text)
                y -= 30
        canvas.showPage()
    canvas.save()
    return path


# A handout page: four slides in a 2x2 grid, so lines of the left and right slides sit at
# the same heights. Bullet text starts well after its marker, as in exported slides
HANDOUT = [
    ("Mitosis", ["Divides one nucleus into two", "Keeps the chromosome number"]),
    ("Meiosis", ["Makes four sex cells", "Halves the chromosome number"]),
    ("Cytokinesis", ["Splits the cytoplasm", "Follows mitosis"]),
    ("Interphase", ["The cell grows", "DNA is copied"]),
]


def build_handout_pdf(path: Path) -> Path:
    canvas = Canvas(str(path), pagesize=letter)
    for i, (title, bullets) in enumerate(HANDOUT):
        x = LEFT + (i % 2) * 250
        y = TOP - (i // 2) * 300
        canvas.setFont(BOLD, 14)
        canvas.drawString(x, y, title)
        canvas.setFont(REGULAR, 9)
        for n, text in enumerate(bullets):
            canvas.drawString(x, y - 24 - n * 14, "•")
            canvas.drawString(x + 16, y - 24 - n * 14, text)
    canvas.showPage()
    canvas.save()
    return path


# (label, x, y of the label, x, y the leader line points to), PDF points
CELL_LABELS = [
    ("Cell membrane", 380, 620, 330, 610),
    ("Nucleus", 380, 560, 255, 555),
    ("Nucleolus", 380, 530, 245, 540),
    ("Mitochondrion", 380, 480, 300, 470),
    ("Cytoplasm", 80, 470, 160, 500),
]
HEART_LABELS = ["Aorta", "Atrium", "Ventricle", "Valve"]  # baked into a picture
RIBOSOME_LABELS = ["Large subunit", "Small subunit", "Messenger RNA"]  # text next to strips
SLIDE_COLOR = (70, 130, 180)  # the slide background picture on page 3 (blue: unlike the figure)
NOTE_COLOR = (250, 240, 150)  # a sticky note drawn on it


def diagram_picture() -> Image.Image:
    """A labeled drawing whose labels are pixels, not text, so only OCR can read them."""
    image = Image.new("RGB", (900, 600), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=34)
    draw.ellipse((250, 120, 650, 520), outline="darkred", width=6)
    draw.line((250, 320, 650, 320), fill="darkred", width=4)
    for text, (x, y), (tx, ty) in zip(
        HEART_LABELS,
        [(40, 40), (40, 230), (680, 430), (690, 250)],
        [(400, 125), (300, 220), (550, 450), (600, 320)],
        strict=True,
    ):
        draw.text((x, y), text, fill="black", font=font)
        left, top, right, bottom = draw.textbbox((x, y), text, font=font)
        start = right + 8 if tx > right else left - 8
        draw.line((start, (top + bottom) / 2, tx, ty), fill="gray", width=3)
    return image


def build_diagram_pdf(path: Path) -> Path:
    """Page 1: a drawn cell with text labels and a table that isn't a diagram. Page 2: a
    picture with its labels baked in, and picture bullets that aren't diagrams. Page 3: a
    slide, a picture under a drawn sticky note, with a figure cut into strips on top and
    text labels next to it."""
    canvas = Canvas(str(path), pagesize=letter)
    canvas.setFont(BOLD, 20)
    canvas.drawString(LEFT, TOP, "The Animal Cell")
    canvas.setFont(REGULAR, BODY)
    canvas.drawString(LEFT, TOP - 30, "Every animal cell has the same basic parts, shown below.")
    canvas.ellipse(130, 440, 330, 640)  # cell
    canvas.circle(240, 550, 35)  # nucleus
    canvas.circle(245, 540, 8)  # nucleolus
    canvas.ellipse(285, 460, 315, 480)  # mitochondrion
    canvas.ellipse(160, 590, 190, 610)  # another mitochondrion
    canvas.setFont(REGULAR, 10)
    for text, x, y, tx, ty in CELL_LABELS:
        canvas.drawString(x, y, text)
        canvas.line(x - 4 if x > tx else x + 70, y + 3, tx, ty)

    rows = [("Organelle", "Job"), ("Ribosome", "Makes proteins"), ("Vacuole", "Stores water")]
    for r, (left, right) in enumerate(rows):  # a ruled table: lines, but not a figure
        y = 300 - r * 20
        canvas.drawString(LEFT + 6, y + 6, left)
        canvas.drawString(LEFT + 156, y + 6, right)
        canvas.line(LEFT, y, LEFT + 300, y)
    canvas.line(LEFT, 340, LEFT + 300, 340)
    for x in (LEFT, LEFT + 150, LEFT + 300):
        canvas.line(x, 260, x, 340)
    canvas.showPage()

    canvas.setFont(BOLD, 20)
    canvas.drawString(LEFT, TOP, "The Heart")
    canvas.drawImage(ImageReader(diagram_picture()), LEFT, 300, width=450, height=300)
    canvas.setFont(REGULAR, BODY)
    dot = Image.new("RGB", (20, 20), "navy")
    for n, text in enumerate(["Pumps blood", "Has four chambers"]):
        canvas.drawImage(ImageReader(dot), LEFT, 250 - n * 18, width=8, height=8)
        canvas.drawString(LEFT + 14, 250 - n * 18, text)
    canvas.showPage()

    canvas.drawImage(ImageReader(Image.new("RGB", (50, 40), SLIDE_COLOR)), 50, 250, 500, 400)
    canvas.setFillColorRGB(*(c / 255 for c in NOTE_COLOR))
    canvas.rect(80, 280, 440, 340, stroke=0, fill=1)
    figure = Image.new("RGB", (300, 300), "white")
    ImageDraw.Draw(figure).ellipse((40, 40, 260, 260), fill="sienna")
    strips = 10  # each strip is 20 points high, too small to be a figure on its own
    for n in range(strips):
        strip = figure.crop((0, n * 30, 300, (n + 1) * 30))
        canvas.drawImage(ImageReader(strip), 120, 560 - (n + 1) * 20, 200, 20)
    canvas.setFillColorRGB(0, 0, 0)
    canvas.setFont(REGULAR, 10)
    for n, text in enumerate(RIBOSOME_LABELS):
        canvas.drawString(330, 520 - n * 60, text)
    canvas.showPage()
    canvas.save()
    return path


if __name__ == "__main__":
    out = Path(__file__).parent / "fixtures"
    print(build_cells_pdf(out / "cells.pdf"))
    print(build_two_column_pdf(out / "two_column.pdf"))
    print(build_slides_pdf(out / "slides.pdf"))
    print(build_handout_pdf(out / "handout.pdf"))
    print(build_diagram_pdf(out / "diagram.pdf"))
    diagram_picture().save(out / "heart.png")
    print(out / "heart.png")
