"""Download the example and held-out documents from their publishers, check each against
its pinned SHA-256, and cut out the parts used. Nothing third-party is kept in git.

    python eval/fetch.py examples   # writes examples/files/
    python eval/fetch.py holdout    # writes eval/holdout/docs/

The downloads are kept in .cache/sources/, so a second run needs no network. A checksum
that doesn't match stops the run: the publisher changed the file, and the gold cards were
written for the old one. Sources and licenses are listed in examples/README.md and
eval/holdout/README.md.
"""

import hashlib
import sys
import urllib.request
from pathlib import Path

import pypdfium2 as pdfium

ROOT = Path(__file__).parent.parent
CACHE = ROOT / ".cache" / "sources"

# name: (url, sha256)
SOURCES = {
    "nasa-rockets.pdf": (
        "https://nasa.gov/wp-content/uploads/2012/07/rockets-educator-guide-20.pdf",
        "e973d4bdf4a48eefbd159b130e1d401fab5f4fe0e617d1c9167f73dfad455438",
    ),
    "nist-csf2-slides.pdf": (
        "https://csrc.nist.gov/csrc/media/Presentations/2024/nist-csf-2-0-overview-and-updates/"
        "11.6.24-4b_CSF_Panel-Quinn.pdf",
        "2e742b4684952a1e5a846c1980a9416d3ec064f2013e6e9cd4920a0d28887d1e",
    ),
    "nist-sp800-12r1.pdf": (
        "https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-12r1.pdf",
        "1baa0b89fc554c15b465b6a974be0a63b08124bf5d5987d34e0965fbafea4a2e",
    ),
    "durrani-2024.pdf": (
        "https://bmcmededuc.biomedcentral.com/counter/pdf/10.1186/s12909-024-05479-y.pdf",
        "a86a709afdef6bb8c057efc3013fb5313ebe6267600cdc76730834e30dc0f9d6",
    ),
    "animal-cell.png": (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/4/48/"
        "Animal_cell_structure_en.svg/1280px-Animal_cell_structure_en.svg.png",
        "e5f145bc57466c59358993b8a9e053405c7fa7bf1323b4169c89cc91c3d518fa",
    ),
}


def source(name: str) -> Path:
    """The downloaded file, fetched once and checked against its checksum."""
    path = CACHE / name
    url, sha256 = SOURCES[name]
    if not path.exists():
        print(f"Downloading {url}")
        CACHE.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "autoflashcards-eval"})
        with urllib.request.urlopen(request, timeout=120) as response:
            path.write_bytes(response.read())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != sha256:
        path.unlink()
        sys.exit(f"Error: {name} changed at the source (SHA-256 {digest}, expected {sha256})")
    return path


def pages(name: str, numbers: list[int], out: Path) -> None:
    """The given pages (1-based) of a PDF, as a new PDF."""
    document, extract = pdfium.PdfDocument(source(name)), pdfium.PdfDocument.new()
    extract.import_pages(document, [n - 1 for n in numbers])
    extract.save(out)
    extract.close()
    document.close()


def handout(name: str, out: Path) -> None:
    """A slide deck printed as a handout: four slides per portrait page, two by two, like
    PowerPoint's "4 slides per page"."""
    document, sheet = pdfium.PdfDocument(source(name)), pdfium.PdfDocument.new()
    width, height, margin, gap = 612, 792, 36, 54
    for first in range(0, len(document), 4):
        page = sheet.new_page(width, height)
        for i in range(first, min(first + 4, len(document))):
            slide_width, slide_height = document[i].get_size()
            scale = (width - 2 * margin - gap) / 2 / slide_width
            column, row = (i - first) % 2, (i - first) // 2
            x = margin + column * (slide_width * scale + gap)
            y = height * (3 - 2 * row) / 4 - slide_height * scale / 2  # centered in its half
            slide = document.page_as_xobject(i, sheet).as_pageobject()
            slide.transform(pdfium.PdfMatrix().scale(scale, scale).translate(x, y))
            page.insert_obj(slide)
        page.gen_content()
    sheet.save(out)
    sheet.close()
    document.close()


def crop(name: str, page_number: int, box: tuple[float, float, float, float], out: Path):
    """A region of a PDF page (x0, top, x1, bottom in points) as a 200 dpi PNG."""
    document = pdfium.PdfDocument(source(name))
    page = document[page_number - 1]
    width, height = page.get_size()
    x0, top, x1, bottom = box
    image = page.render(scale=200 / 72, crop=(x0, height - bottom, width - x1, top)).to_pil()
    image.save(out)
    document.close()


def examples() -> Path:
    out = ROOT / "examples" / "files"
    out.mkdir(parents=True, exist_ok=True)
    # "How Rockets Work" and "Applying Newton's Laws" (printed pages 22-31)
    pages("nasa-rockets.pdf", list(range(28, 38)), out / "rockets.pdf")
    # the solid propellant rocket on printed page 28: its labels are part of the picture
    crop("nasa-rockets.pdf", 34, (316, 334, 432, 590), out / "solid-rocket.png")
    return out


def holdout() -> Path:
    out = ROOT / "eval" / "holdout" / "docs"
    out.mkdir(parents=True, exist_ok=True)
    pages("nist-csf2-slides.pdf", list(range(1, 11)), out / "csf-slides.pdf")
    handout("nist-csf2-slides.pdf", out / "csf-handout.pdf")
    # section 1.4 Important Terminology and chapter 3 Roles and Responsibilities
    pages("nist-sp800-12r1.pdf", [12, 13, *range(23, 30)], out / "sp800-12.pdf")
    pages("durrani-2024.pdf", list(range(1, 9)), out / "spaced-repetition.pdf")
    (out / "animal-cell.png").write_bytes(source("animal-cell.png").read_bytes())
    return out


if __name__ == "__main__":
    builders = {"examples": examples, "holdout": holdout}
    if len(sys.argv) != 2 or sys.argv[1] not in builders:
        sys.exit(f"Usage: python eval/fetch.py {{{'|'.join(builders)}}}")
    print(f"Wrote {builders[sys.argv[1]]()}")
