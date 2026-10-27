# Changelog

## Unreleased

- AI cards: `--ai claude` (Claude Haiku 5.5 by default, `anthropic` SDK structured output), `--ai claude-code` (runs `claude -p` on a Claude Pro/Max plan, no API key) or `--ai ollama` (local), with `--model`. Text goes in chunks of about 3,000 tokens; every card should quote its source line; cards whose quote, term or answer isn't in the document are dropped. One retry on a malformed reply, then the chunk is skipped with a warning; replies are cached on disk; requests and an input-token estimate are printed first. Install with `pip install ".[ai]"`.
- Eval with `--ai claude-code`: recall 80% → 94%, precision 100% → 56% (many extra AI cards are sound but outside the term-only gold set), no card obeyed the hidden instruction.
- Eval with `--ai ollama` (llama3.2 3B, local): recall 97%, precision 77%, no card obeyed the hidden instruction. Cards without a quote (small models often leave it empty) are kept when both term and answer come from the text. Ollama requests use a 16K context and a 4,096-token reply cap: the default 4K context left no room to answer and the model never stopped. The JSON schema also goes in the prompt, as Ollama's docs advise.
- Eval: a hostile document with a hidden instruction aimed at AI models, an *Injected* column counting cards that obey it, and `eval/score.py --ai`. CI's `eval-ai` job runs it on manual trigger only.

- `definition_sentence`: "X means Y" (before a noun phrase or "-ing" word), one cloze deletion per defining clause ("X means A, and Y means B" → c1, c2), and appositives ("Retention, the share of customers who return, is…"). Fixed: the sentence-start capital check was case-insensitive, so lowercase fragments could become cards. Eval recall 71% → 81%, precision unchanged at 100%; no change on the real PDFs checked.
- `eval/score.py` counts each cloze deletion as a question, and each question claims only its closest gold card.

- Evaluation: `eval/score.py` scores the rules against hand-written gold cards for four generated documents (handout, slide deck, two-column article, textbook) and writes `outputs/eval.md`; `--private` scores your own PDFs in the git-ignored `eval/private/`. Baseline: 100% precision, 71% recall over 31 gold cards. CI's new `e2e` job runs it on every push.

- PDF slide handouts (several slides per page): page layout is split into text boxes by recursive XY-cut, so slides are read one at a time and two-column articles with narrow gutters are read column by column. Lines that stop short of their box's edge end an item even without a period, and a `Term = …` line always starts a new one.
- Headings are judged against each page's body text size (pages with little text use the document's), and large prose that carries on into a lowercase line isn't a heading.
- `slide_title_bullets` stays on the title's page, and accepts short paragraphs without a closing period as bullets (slides whose bullet markers are pictures).
- `term_colon` skips contact labels (`E-mail:`, `Tel:`, `DOI:`…) and terms with unbalanced parentheses.

- Slide rules: `bold_term_bullets` (an all-bold bullet and the bullets that explain it) and `slide_title_bullets` (a slide title and its bullets, for short all-bullet sections only). Rules now see the blocks after the one they start from.
- `term_colon` also accepts `=`, `→` and `->` as separators; decades ("1970s") aren't terms.
- Card backs with several bullets show one per line in Anki.
- Sections headed Table of contents, Thanks, Questions or Credits are skipped, judged by the nearest heading only. Number-only lines ("11.2" on divider slides) are no longer headings.
- PDF text: when letter boxes overlap (PowerPoint exports have wrong glyph widths), the PDF's own space characters are used instead of gap measurement, which fixes run-together words in exported slides.

- New rules: `bold_lead` (a bold term followed by text) and `definition_sentence` ("X is a…", "X refers to…" sentences become cloze cards). Rules run in order and the first match per block wins. `--rules` picks a subset.
- Filter stage: cards with the same front, near-duplicates (rapidfuzz ratio ≥ 90) and overly long or empty cards are dropped, with a reason.
- `--csv` writes an Anki text-import file with file headers (built-in Basic and Cloze note types, same note IDs as the `.apkg`). `--json` writes blocks, cards and dropped cards.
- Running headers and footers are found on 40% of pages instead of half, which catches books that alternate left and right page footers.

- PDF input (pdfplumber). The structure stage finds headings by font size and bold text, removes running headers, footers and page numbers, joins wrapped lines and hyphenated words, and reads two-column pages left column first. Cards from PDFs show their page number.
- Word spacing scales with font size, and duplicated glyphs are removed, which fixes run-together and split words in some typeset PDFs. Glyphs the PDF doesn't map to text become U+FFFD; at the start of a line they are read as bullets.
- `term_colon` skips figure and table captions, `Keywords:`/`Abstract:` labels, and anything under a References or Bibliography heading.
- Test PDFs are generated by `tests/make_fixtures.py` (reportlab, dev only).

- Markdown to `.apkg`: `autoflashcards notes.md` reads headings, list items and paragraphs, makes cards from "Term: definition" lines, and writes an Anki deck.
- Each card shows its source file and heading path, and is tagged with its headings and the rule that made it.
- Note IDs come from the deck name and the card front, so re-importing an edited file updates cards instead of duplicating them.

- Project skeleton: `src/` package, `autoflashcards` command (`--help`, `--version`), MIT license.
- CI: ruff lint and format check, tests on Python 3.11 and 3.14 on Linux and Windows, gitleaks.
