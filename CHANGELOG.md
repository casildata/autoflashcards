# Changelog

## Released

- Diagram cards (`--diagrams`): each labeled figure becomes an Anki Image Occlusion note (Anki 23.10+) with a box over every label and one card per box. Labels come from the PDF's text or Tesseract OCR. The back shows the card's label and its source. Boxes can be fixed in Anki's occlusion editor and labels in the `Image Labels` field.
  - A Box Numbers button on the back shows which `Image Labels` line each box is. It and Toggle Masks keep their setting when you edit the note.
  - `--type-answers` adds a box to type each label.
  - `--sio` writes notes for the Simple Image Occlusion add-on instead. `--link-pdf` links each note to its PDF page.
  - Decks from earlier versions: delete the `Image Occlusion (autoflashcards)` note type in Anki before importing a new deck.
- `--preview` lists the cards instead of writing a deck. A locked output file gives a clear error instead of a traceback.
- `--csv` opens cleanly in Excel.
- Progress bars for the slow steps, and a summary at the end of a run: cards per rule, diagrams, dropped cards by reason, deck size, time, and how to import the deck.
- CI: license check and `pip-audit`.
- AI cards: `--ai claude`, `--ai claude-code` or `--ai ollama`. Cards whose quote or answer isn't in the document are dropped.
- Eval: hand-judged precision, and a hostile document that tests whether AI cards obey a hidden instruction. With `--ai claude-code`, recall is 94% and precision 86%. With `--ai ollama` (llama3.2 3B), recall is 97% and precision 84%. Neither obeyed the hidden instruction.

## Earlier Version

- `definition_sentence` handles "X means Y", several definitions in one sentence, and appositives. Eval recall 71% → 81%.
- Evaluation: `eval/score.py` scores the rules against hand-written gold cards and runs in CI. Baseline: 100% precision, 71% recall.
- Slide handouts with several slides per page are read slide by slide, and two-column articles column by column.
- Slide rules: `bold_term_bullets` and `slide_title_bullets`.
- Rules: `bold_lead` and `definition_sentence`. `--rules` picks a subset.
- Duplicate, near-duplicate and overlong cards are filtered out. `--csv` and `--json` outputs.
- PDF input: headings, running headers and footers, wrapped lines and two-column pages. Cards show their page number.
- Markdown to `.apkg`. Cards show their source and are tagged by heading and rule. Re-imports update cards instead of duplicating them.
- Project skeleton, MIT license, and CI (lint, tests on Linux and Windows, gitleaks).
