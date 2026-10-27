# Changelog

## Unreleased

- Markdown to `.apkg`: `autoflashcards notes.md` reads headings, list items and paragraphs, makes cards from "Term: definition" lines, and writes an Anki deck.
- Each card shows its source file and heading path, and is tagged with its headings and the rule that made it.
- Note IDs come from the deck name and the card front, so re-importing an edited file updates cards instead of duplicating them.

- Project skeleton: `src/` package, `autoflashcards` command (`--help`, `--version`), MIT license.
- CI: ruff lint and format check, tests on Python 3.11 and 3.14 on Linux and Windows, gitleaks.
