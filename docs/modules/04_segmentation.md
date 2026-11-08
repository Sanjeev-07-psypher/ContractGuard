# 04 Clause segmentation

Files: `contractguard/segmentation/segmenter.py`; patterns in `config/patterns.yaml: segmentation`.

## What

Splits the cleaned text into `Clause`s in reading order, with ids `c001`, `c002`, ..., the clause
number ("7", "7.2", "VII"), a heading, the text, the page range, a `section_path` and a kind:
`PREAMBLE`, `BODY`, `DEFINITIONS`, `EXHIBIT` or `SIGNATURE`.

## Why

Every later decision is made per clause: the classifier labels clauses, facts are read from the
clauses of one category, and findings point at clauses. If two clauses are merged, a termination
clause can hide inside a payment clause; if one clause is split badly, its sentence loses its
subject.

## How

1. **Choose a mode.** Count numbered headings (level 1 or 2 patterns, not level 3). With fewer
   than `segmentation.fallback_min_headings` (3), use the **paragraph fallback**: split on blank
   lines and merge paragraphs shorter than `fallback_merge_chars`.
2. **Scan lines** (`_scan`):
   - A level 1 heading ("7. Payment", "ARTICLE VII", "SECTION 7", or "7 TERM AND RENEWAL") or level 2 heading ("7.2") starts a
     clause. Level 3 items ("(a)", "(i)", "7.2.1") are appended to their parent.
   - For DOCX, a paragraph whose Word style matches `Heading*` also starts a clause.
   - An exhibit heading ("Exhibit A", "Schedule 1", "Annex", "Appendix") starts an `EXHIBIT` clause; clauses after it
     stay exhibits.
   - "IN WITNESS WHEREOF" (or a line starting "Signature" or "By:") starts the `SIGNATURE` block.
   - Text before the first clause is the `PREAMBLE` (parties and date live here).
   - A heading containing "Definitions" or "Interpretation" makes the clause `DEFINITIONS`.
3. **Parse the start line** (`parse_start`): split the number from the rest. The rest is a heading
   only if it is all capitals, or short Title Case text not ending like a sentence (D18).
   "Contract Price and Payment" is a heading; "On termination, the Contractor shall withdraw its"
   is a wrapped sentence. ALL-CAPS headings are converted to Title Case.
4. **OCR-tolerant Roman numerals** (D17): Tesseract reads the "I" of "ARTICLE III" as `l`, `1`,
   `i` or `|`. `_roman_fix` maps those back, so "ARTICLE Ill" becomes "III".
5. **Length guards.** Clauses under `min_chars` (40) merge into the next clause. Clauses over
   `max_chars` (3,000) are split at sentence boundaries into parts with suffixed ids (`c014a`,
   `c014b`); a single sentence longer than the limit stays whole.
6. **Locate.** Each clause gets `page_start` and `page_end` from the offset map, `is_ocr` if any
   part came from OCR, and a `section_path` such as `7 > 7.2`.

## Callers and dependencies

Called by `pipeline.run`. Uses the spaCy sentencizer from `extraction/sentences.py` for long-clause
splits.

## Data in and out

In: `CleanedText` and, optionally, the `Document` (for DOCX styles). Out: `list[Clause]` with
classification fields still empty.

## Errors and edge cases

- Contracts without numbering fall back to paragraphs, so they are still segmented, just less
  precisely.
- A running header that survived cleaning (2-page contracts) is absorbed into a clause; evaluation
  matching tolerates it.
- Lettered sub-items are deliberately merged into their parent, matching how reviewers cite
  clauses ("clause 7.2"), at the cost of very long clauses for heavily nested contracts.

## Configuration

`segmentation.min_chars`, `max_chars`, `fallback_min_headings` in `settings.yaml`;
`segmentation.l1`, `l2`, `l3`, `parse`, `definitions_heading`, `exhibit_heading`, `signature`,
`docx_heading_style`, `heading_max_words`, `fallback_merge_chars` in `patterns.yaml`.

## Alternatives considered

- **A trained sequence model (CRF or transformer) for boundaries**: needs labelled boundary data,
  which does not exist for Indian contracts. Numbered headings are reliable in real contracts.
- **Fixed-size chunks**: break clauses mid-sentence and lose the clause number reviewers need.
- **One clause per paragraph**: splits multi-paragraph clauses.

## Interview notes

- *Measured result?* Boundary F1 1.000 on DOCX and 0.986 on text and scanned PDFs of the 8 gold
  contracts. Optimistic, because the patterns were developed
  on these contracts (D21).
- *How are boundaries scored?* A predicted clause matches a gold clause when its opening contains
  the gold clause's first eight words with a rapidfuzz partial ratio of at least 85, one to one and
  in order.
- *Hardest case?* OCR turning Roman numerals into `l` and `|`, and wrapped sentences that look like
  headings; D17 and D18 handle them.
