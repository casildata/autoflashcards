# Held-out evaluation set

Real documents from four subjects, in the input formats autoflashcards reads, kept apart from
everything the rules were developed on. `eval/gold/` scores the rules on generated documents
they were tuned against; this set is for measuring how they do on documents they weren't.

## Rules

1. **The gold cards were written before autoflashcards was run on these documents.** They
   list what a student should get a card for, taken from the documents themselves, and are
   frozen in the commit that adds them. A later change to a gold file says why in its commit.
2. **Nothing is tuned on this set.** No rule, threshold or prompt is changed to improve a
   score here. If a result here shows a problem, the fix is developed and tested on other
   documents, and this set is re-run to measure it.
3. **Results are reported as they come out**, including the first run.

The gold cards were drafted by Claude Code (an AI assistant) from the source text and
reviewed by the author before the first run.

## Documents

Run `python eval/fetch.py holdout` to download them into `eval/holdout/docs/` (not in git).
Each download is checked against a pinned SHA-256, so the documents can't change under the
gold cards.

| File | Format | Subject | Source | License |
|---|---|---|---|---|
| `csf-slides.pdf` | slide deck, 10 slides | cybersecurity | S. Quinn, *NIST Cybersecurity Framework 2.0: Overview & Updates*, NIST, November 2024 ([PDF](https://csrc.nist.gov/csrc/media/Presentations/2024/nist-csf-2-0-overview-and-updates/11.6.24-4b_CSF_Panel-Quinn.pdf)) | Work of the US Government, not subject to copyright in the US |
| `csf-handout.pdf` | handout, 4 slides per page | cybersecurity | the same deck, laid out 2 × 2 per page by `eval/fetch.py` | same |
| `sp800-12.pdf` | textbook-style guide, 9 pages | cybersecurity | M. Nieles, K. Dempsey, V. Pillitteri, *An Introduction to Information Security*, NIST SP 800-12 Rev. 1, 2017 ([doi:10.6028/NIST.SP.800-12r1](https://doi.org/10.6028/NIST.SP.800-12r1)): pages 2-3 (§1.4 Important Terminology) and 13-19 (Ch. 3 Roles and Responsibilities) | Work of the US Government, not subject to copyright in the US |
| `spaced-repetition.pdf` | two-column research article, 8 pages | medical education | S. F. Durrani et al., "Effectiveness of spaced repetition for clinical problem solving amongst undergraduate medical students studying paediatrics in Pakistan", *BMC Medical Education* 24:676 (2024) ([doi:10.1186/s12909-024-05479-y](https://doi.org/10.1186/s12909-024-05479-y)) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); unchanged |
| `animal-cell.png` | labeled diagram (picture) | biology | LadyofHats (Mariana Ruiz), *Animal cell structure* ([Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Animal_cell_structure_en.svg)), 1280 px rendering | Released into the public domain by its author |

Changes: the SP 800-12 file holds 9 of the publication's 101 pages, and the handout is a new
layout of the slides; nothing else is edited.

## Gold files

- `gold/<document>.jsonl`: one `{"term": ..., "fact": ...}` per line, the format of
  `eval/gold/`. `csf-handout.pdf` uses `gold/csf-slides.jsonl`: same slides, different layout.
- `gold/diagrams.json`: the labels on each labeled figure, in reading order, for scoring
  diagram labels (OCR or text layer). A label that appears twice is listed twice.

Gold cards cover what a student should learn from the document, including facts that only
appear in pictures (the CSF 2.0 Functions are on the wheel graphic). The rules can't read
pictures, so those count as misses: that is part of what this set measures.
