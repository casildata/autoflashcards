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

| Option | Does |
|---|---|
| `--out FILE` | Where to write the deck (default: the first input's name, `.apkg`) |
| `--deck NAME` | Deck name in Anki (default: the first input's name) |
| `--csv` | Also write a `.csv` for Anki's text import (Anki 2.1.55+, built-in Basic and Cloze note types) |
| `--json` | Also write a `.json` with everything extracted, every card, and every dropped card with the reason. Written even when no cards are found, which is when it helps most |
| `--rules a,b` | Use only these rules (see below) |

## How cards are made

Each paragraph or bullet is checked against these rules in order; the first one that matches makes the card(s), so one fact doesn't become two cards.

| Rule | Your notes say | Card |
|---|---|---|
| `term_colon` | `Osmosis: movement of water across a membrane.` (or `=`, `→`, `->`) | **Osmosis** → movement of water across a membrane. |
| `bold_lead` | **Mitosis** divides a cell into two identical cells. | **Mitosis** → divides a cell into two identical cells. |
| `definition_sentence` | A ribosome is a structure that builds proteins. | Cloze: A [...] is a structure that builds proteins. |
| `bold_term_bullets` | • **Protein kinases**<br>&nbsp;&nbsp;– Transfer phosphates from ATP to proteins | **Protein kinases** → Transfer phosphates from ATP to proteins |
| `slide_title_bullets` | Slide title *G protein-coupled receptor*, then its bullets | **G protein-coupled receptor** → its first three bullets |

`definition_sentence` looks for "X is a / are the / was an / is defined as / is called / is known as / refers to …", and skips sentences whose subject is a pronoun ("It is a…", "There are…").

The last two rules are for lecture slides, including slides exported to PDF. A card's back holds up to three bullets, one per line. `slide_title_bullets` only uses short sections made entirely of bullets (up to 8) on the slide's own page, so the headings of a textbook or article don't turn into list cards. It also skips titles that describe a picture ("Image of…", "Example of…", "Illustration of…") and slides whose bullets are already `Term: definition` cards.

Skipped everywhere: figure and table captions, labels such as `Note:` or `Keywords:`, and sections headed References, Bibliography, Table of contents, Thanks or Credits. Cards with the same front, near-identical cards (90% similar or more) and overly long cards are dropped; `--json` lists them.

For PDFs, headings are found by font size and bold text, running headers, footers and page numbers are removed, and two-column pages are read left column first. Handouts with several slides per page are read slide by slide, and each page's own body text size is used to tell headings from bullets, since every slide on a handout can be scaled differently. Bullets whose markers are pictures (common in exported slides) count as bullets when they are short and have no closing period.

**Not yet supported:** scanned PDFs (pages that are images, with no text layer) produce no cards; OCR is planned. In PDFs, sub-bullets aren't told apart from bullets, so a bold term's back is "the bullets after it, up to the next bold term or slide".

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
| Rule | `afg::rule::term_colon` | Which autoflashcards rule made the card (`afg` = autoflashcards), named as in the table above. |

Useful searches in the Anki browser:

| Search | Finds |
|---|---|
| `tag:cell_biology::transport` | Cards from the Transport section, including its subsections |
| `tag:afg::*` | Every card autoflashcards made |
| `tag:afg::rule::term_colon` | Cards from one rule, for example to review or bulk-delete them if that rule doesn't suit your notes |

**Re-importing.** Each card is identified by its deck name and its front. If you fix your notes and import again, with Anki's default import settings existing cards are updated in place and your review history is kept, so you don't get duplicates. Changing a card's front, or the deck name, makes it a new card.
