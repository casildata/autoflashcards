# autoflashcards

[![pipeline](https://github.com/casildata/autoflashcards/actions/workflows/pipeline.yml/badge.svg)](https://github.com/casildata/autoflashcards/actions/workflows/pipeline.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

Turn PDFs, slides and notes into Anki-ready flashcard decks.

**Status:** early development. PDF and Markdown input work today.

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
| `--ai claude` / `claude-code` / `ollama` | Also make cards with a language model (see [AI cards](#ai-cards-optional)) |
| `--model NAME` | Model for `--ai` (default: `claude-haiku-5-5`, or `llama3.2` for Ollama) |

## How cards are made

Each paragraph or bullet is checked against these rules in order; the first one that matches makes the card(s), so one fact doesn't become two cards.

| Rule | Your notes say | Card |
|---|---|---|
| `term_colon` | `Osmosis: movement of water across a membrane.` (or `=`, `→`, `->`) | **Osmosis** → movement of water across a membrane. |
| `bold_lead` | **Mitosis** divides a cell into two identical cells. | **Mitosis** → divides a cell into two identical cells. |
| `definition_sentence` | A ribosome is a structure that builds proteins. | Cloze: A [...] is a structure that builds proteins. |
| `bold_term_bullets` | • **Protein kinases**<br>&nbsp;&nbsp;– Transfer phosphates from ATP to proteins | **Protein kinases** → Transfer phosphates from ATP to proteins |
| `slide_title_bullets` | Slide title *G protein-coupled receptor*, then its bullets | **G protein-coupled receptor** → its first three bullets |

`definition_sentence` looks for "X is a / are the / was an / is defined as / is called / is known as / refers to / means …" at the start of a sentence, and skips sentences whose subject is a pronoun ("It is a…", "There are…"). A sentence that defines two terms ("Homozygous means having two identical alleles, and heterozygous means…") becomes one cloze note with two deletions, so Anki quizzes each. It also catches a term followed by its description between commas: "{{c1::Retention}}, the share of customers who come back, is…".

The last two rules are for lecture slides, including slides exported to PDF. A card's back holds up to three bullets, one per line. `slide_title_bullets` only uses short sections made entirely of bullets (up to 8) on the slide's own page, so the headings of a textbook or article don't turn into list cards. It also skips titles that describe a picture ("Image of…", "Example of…", "Illustration of…") and slides whose bullets are already `Term: definition` cards.

Skipped everywhere: figure and table captions, labels such as `Note:` or `Keywords:`, and sections headed References, Bibliography, Table of contents, Thanks or Credits. Cards with the same front, near-identical cards (90% similar or more) and overly long cards are dropped; `--json` lists them.

For PDFs, headings are found by font size and bold text, running headers, footers and page numbers are removed, and two-column pages are read left column first. Handouts with several slides per page are read slide by slide, and each page's own body text size is used to tell headings from bullets, since every slide on a handout can be scaled differently. Bullets whose markers are pictures (common in exported slides) count as bullets when they are short and have no closing period.

**Not yet supported:** scanned PDFs (pages that are images, with no text layer) produce no cards; OCR is planned. In PDFs, sub-bullets aren't told apart from bullets, so a bold term's back is "the bullets after it, up to the next bold term or slide".

## AI cards (optional)

The rules only catch facts written in recognizable patterns. `--ai` also sends the text to a language model, which can write cards from plain statements like "Producers capture energy from sunlight". Rule cards are kept first; AI cards that repeat them are dropped as duplicates. AI cards are tagged `afg::rule::ai_<backend>`.

```
pip install ".[ai]"
autoflashcards lecture3.pdf --ai claude-code   # your Claude Pro or Max plan, through Claude Code
autoflashcards lecture3.pdf --ai claude        # Anthropic API: needs ANTHROPIC_API_KEY and API credit
autoflashcards lecture3.pdf --ai ollama        # a local model: nothing leaves your computer
```

| Backend | Needs | Pays with |
|---|---|---|
| `claude-code` | [Claude Code](https://code.claude.com) installed and logged in | your Claude Pro/Max plan's usage limits; no API key |
| `claude` | `ANTHROPIC_API_KEY` from [the Console](https://console.anthropic.com) | prepaid API credit (Pro doesn't include any) |
| `ollama` | [Ollama](https://ollama.com) running, `ollama pull llama3.2` | nothing; runs on your computer (a 3B model fits a 6 GB GPU) |

`claude-code` runs `claude -p` with its own system prompt, no tools (no file, shell or web access), a JSON schema for the reply and no saved session, from an empty folder so your projects' `CLAUDE.md` files aren't sent.

- **Privacy:** `--ai claude` and `--ai claude-code` send your file's text to Anthropic (a notice says so the first time). `--ai ollama` talks only to Ollama on your computer (`OLLAMA_HOST` to change where).
- **Cost:** it prints the number of requests and an estimate of input tokens first. A chapter is a few requests to Claude Haiku 5.5. Replies are cached on disk, so running the same file again costs nothing.
- **Checked, not trusted:** the model is asked to quote the line each card came from. Cards whose quote isn't in your file, or whose answer is mostly words your file doesn't use, are dropped, and the run says how many. The quote also gives the card its real page and heading. Small local models often leave the quote out; those cards are kept only if their term also comes from your file, and are placed where their words fit best.
- **Prompt injection:** the file's text is sent as data inside `<document>` tags and the model is told not to follow instructions in it. The eval includes a document with a hidden instruction aimed at AI models, and counts any card that obeys it.
- If a request fails, that part of the file is skipped with a warning. A missing key, a stopped Ollama or an unknown model stops the run (exit code 2).

## How well it works

`eval/score.py` builds five test documents with original text, in layouts taken from real course material, and checks the cards against hand-written gold cards: what a student should get a card for. The gold cards were written before running the tool, so they include facts no rule catches yet.

| Document | Layout | Gold | Cards | Precision | Recall |
|---|---|---:|---:|---:|---:|
| handout | 4 slides per page, bullets drawn as pictures, a notes column, a chart slide | 10 | 7 | 100% | 70% |
| deck | one slide per page: divider, bold sub-terms, arrows, picture and "Questions?" slides | 6 | 5 | 100% | 83% |
| article | two columns with a narrow gutter, abstract, keywords, figure caption, references | 6 | 6 | 100% | 100% |
| textbook | single column, running header, page numbers, bold terms | 9 | 6 | 100% | 78% |
| hostile | short notes plus a hidden instruction aimed at AI models | 4 | 3 | 100% | 75% |
| **All** | | 35 | 27 | **100%** | **80%** |

With AI cards added, on the same documents:

| | Rules only | + Claude Haiku 5.5 (`claude-code`) | + Llama 3.2 3B (`ollama`, local) |
|---|---:|---:|---:|
| Cards | 27 | 57 | 43 |
| Recall | 80% | **94%** | **97%** |
| Precision | **100%** | 86% | 84% |
| Cards obeying the hidden instruction | 0 | **0** | **0** |

Both models find the plain-statement facts the rules miss. The gold set lists key terms only, so the AI cards it doesn't list were checked by hand (`eval/gold/<name>.judged.jsonl`): most are sound ("Examples of abiotic factors → Temperature, water, light and soil", "Range of an RFM score → 111 to 555"). What costs precision is repeats of rule-card facts in another form (5 cards with each model, plus 3 Haiku cloze cards) and, for Llama, definitions it made up from a slide title or figure caption ("Energy Flow → the movement of energy through an ecosystem"). `outputs/eval-<backend>.md` lists every card. On a real 4-slides-per-page lecture handout, the AI took the deck from 19 to 36 cards in one request.

*Precision* is the share of cards that match a gold card or were judged correct by hand; repeats, wrong cards and cards with no verdict yet (*unjudged*, listed in the report) count against it. *Recall* is the share of gold cards found (one cloze note with two deletions can find two). Missed today: facts phrased as plain statements ("Producers capture energy from sunlight", "Dominant alleles hide the effect of recessive ones"). Telling those apart from any other sentence needs grammar analysis or the AI stage. Real PDFs are messier than these documents, so expect lower precision on your own files.

```
python eval/score.py              # writes outputs/eval.md and a deck per document
python eval/score.py --private    # scores eval/private/<name>.pdf against <name>.jsonl
python eval/score.py --ai claude  # rules + AI cards; writes outputs/eval-claude.md
```

To score your own PDFs, put them in `eval/private/` (ignored by git) with a `<name>.jsonl` beside each, one `{"term": "...", "fact": "..."}` per line. CI runs the rules eval on every push and shows the table in the run summary; the rules + Claude eval runs only when started by hand, since it calls the API.

## Reading your cards in Anki

**The source line.** Under each answer, a small grey line shows where the card came from:

```
cells.md · Cell Biology › Transport
```

That is the file, then the headings the line sat under. For PDFs it also shows the page (`notes.pdf · p.12 · Cells › Transport`), so you can check a card against your notes.

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

## License

MIT. Dependencies are under permissive licenses (MIT, BSD, Apache-2.0, ISC, PSF), except `frozendict` (LGPL-3.0), which `genanki` needs to write `.apkg` files. It is installed as a separate, unmodified package, so it doesn't change this project's license. CI fails if any other GPL-family package, or one that states no license, is added, runs `pip-audit` for known vulnerabilities and scans the history for committed secrets.
