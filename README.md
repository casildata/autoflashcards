# autoflashcards

[![pipeline](https://github.com/casildata/autoflashcards/actions/workflows/pipeline.yml/badge.svg)](https://github.com/casildata/autoflashcards/actions/workflows/pipeline.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

Turn PDFs, slides and notes into Anki-ready flashcard decks.

**Status:** early development. PDF and Markdown input work today; PowerPoint is next.

## Usage

From a clone of this repo:

```
pip install .
autoflashcards lecture3.pdf                   # writes lecture3.apkg
autoflashcards week1.md week2.pdf --deck "Bio 101" --out bio.apkg
```

Then in Anki: **File → Import** and pick the `.apkg` file.

Lines written as `Term: definition` become cards, with the term on the front and the definition on the back. Figure and table captions, labels such as `Note:` and reference lists are skipped.

For PDFs, headings are found by font size and bold text, running headers, footers and page numbers are removed, and two-column pages are read left column first.

**Not yet supported:** scanned PDFs (pages that are images, with no text layer) produce no cards; OCR is planned.

## Reading your cards in Anki

**The source line.** Under each answer, a small grey line shows where the card came from:

```
cells.md · Cell Biology › Transport
```

That is the file, then the headings the line sat under. For PDFs it will also show the page (`p.12`), so you can check a card against your notes.

**Tags.** Every card gets two kinds of tags. Anki shows `::` as a folder tree in the sidebar.

| Tag | Example | Meaning |
|---|---|---|
| Headings | `cell_biology::transport` | The headings the card came from, lowercased with spaces turned into `_`. Click a folder in the sidebar to study one chapter or section. |
| Rule | `afg::rule::term_colon` | Which autoflashcards rule made the card (`afg` = autoflashcards). `term_colon` means it came from a `Term: definition` line. |

Useful searches in the Anki browser:

| Search | Finds |
|---|---|
| `tag:cell_biology::transport` | Cards from the Transport section, including its subsections |
| `tag:afg::*` | Every card autoflashcards made |
| `tag:afg::rule::term_colon` | Cards from one rule, for example to review or bulk-delete them if that rule doesn't suit your notes |

**Re-importing.** Each card is identified by its deck name and its front. If you fix your notes and import again, with Anki's default import settings existing cards are updated in place and your review history is kept, so you don't get duplicates. Changing a card's front, or the deck name, makes it a new card.
