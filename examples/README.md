# Examples

Inputs to try autoflashcards on, one per format it reads. They're for demos and for seeing
what the tool makes; the scored evaluation is in `eval/` (generated documents) and
`eval/holdout/` (real documents, never tuned on).

```bash
python eval/fetch.py examples                      # downloads the NASA pages into examples/files/
autoflashcards examples/newtons-laws.md            # Markdown notes
autoflashcards examples/files/rockets.pdf --diagrams --out rockets.apkg
autoflashcards examples/files/solid-rocket.png     # a labeled picture, read with OCR (needs Tesseract)
```

Double-click the `.apkg` to import it into Anki.

| File | Format | Source | License |
|---|---|---|---|
| `newtons-laws.md` | Markdown notes | written for this project | MIT, like the rest of the repo |
| `files/rockets.pdf` | educator guide, three-column pages with figures, 10 pages | NASA, *Rockets Educator Guide* (MSFC-12-2025-SLS-5576), pages 22-31: "How Rockets Work" and "Applying Newton's Laws" ([PDF](https://nasa.gov/wp-content/uploads/2012/07/rockets-educator-guide-20.pdf)) | "This publication is in the Public Domain and is not protected by copyright." |
| `files/solid-rocket.png` | labeled picture | the solid propellant rocket figure on page 28 of the same guide, rendered at 200 dpi | same |

`files/` isn't in git: `eval/fetch.py` downloads the guide once, checks it against a pinned
SHA-256, and cuts out these pages.
