# 03 Cleaning and normalisation

Files: `contractguard/preprocessing/cleaner.py`, `normalizer.py`; patterns in
`config/patterns.yaml: cleaning`.

## What

Turns a `Document` into `CleanedText`: one string with blocks separated by a blank line, plus a
list of `TextSpan`s that map every stretch of the string back to its block, page and paragraph.

## Why

Raw PDF text is full of noise that breaks later stages: running headers ("Master Services
Agreement - Confidential") repeated on every page, "Page 3 of 9" lines, words hyphenated across
line breaks, sentences broken into short lines, curly quotes and odd dashes. Regular expressions
for facts and headings are far simpler on clean text. The offset map keeps page numbers available
for the report even though the text has changed.

## How

`clean_document(doc)` runs these steps:

1. **Repeating headers and footers** (PDF with at least 3 pages): `find_repeating_lines` looks at
   the top 3 and bottom 3 non-empty lines of each page. A line's key has its digits removed and its
   spaces collapsed, so "Page 2 of 9" and "Page 3 of 9" match. A key that appears in the same zone
   on at least half of the pages is a header or footer, and only lines inside those zones are dropped.
   **Top and bottom are counted separately (D23)**: a sentence that wraps across a page break
   ("... fifteen" / "(15) days' notice" at the foot of one page) once looked like a repeated line
   and was deleted. That bug removed real notice periods from GC04 and was found by the fact
   evaluation.
2. **Page-number lines** such as "3", "Page 3" or "3 of 9" are removed.
3. **De-hyphenation**: "termi-\nnation" becomes "termination".
4. **Soft-wrap joining** inside a block: a line that does not end a sentence, followed by a line
   that starts in lower case (or with "(15) days"), is joined with a space (D24). A clause number
   left alone on its line ("7.2") is joined to the next line.
5. **Character normalisation** (`normalize_chars`): curly quotes to straight quotes, all dashes to
   "-", non-breaking and other spaces to a plain space, soft hyphens removed, repeated spaces
   collapsed, then Unicode NFKC.

Steps 2 to 5 run per block, so each kept block becomes exactly one `TextSpan`.

## Callers and dependencies

Called by `pipeline.run`. Consumed by the segmenter, which uses `CleanedText.span_at` and
`pages_for` to give clauses page numbers.

## Data in and out

In: `Document`. Out: `CleanedText(text, spans, file_type, removed_lines)`. `removed_lines` lists
the dropped headers for debugging.

## Errors and edge cases

- Short documents (1 to 2 pages) skip header removal: with so few pages, repetition is not
  evidence (D15). A header on a 2-page contract stays in the text; the segmenter tolerates it.
- Case, stop words and punctuation are kept on purpose: "not", "unless" and "except" change legal
  meaning. Lowercasing happens only inside the TF-IDF vectoriser.

## Configuration

`cleaning.header_footer_lines` (3), `header_footer_min_ratio` (0.5), `header_footer_min_pages` (3),
and the regexes `page_number_line`, `dehyphenate`, `soft_wrap_end`, `soft_wrap_next`,
`number_only_line`.

## Alternatives considered

- **Remove the first and last line of every page blindly**: deletes real text on pages without a
  header.
- **Layout analysis with font sizes and positions**: more accurate but much more complex, and OCR
  output has no font information.
- **Lowercasing and stop-word removal here**: would destroy negations needed by fact extraction.

## Interview notes

- *Why keep an offset map?* Cleaning changes character positions; the map lets any clause found
  later report the page it came from.
- *What is NFKC?* Unicode compatibility normalisation: it folds look-alike characters (for example
  full-width digits or the "ﬁ" ligature) into their plain forms, so regexes match.
- *Tell me about a bug here.* D23: a sentence wrapped across a page break was taken for a running
  header and deleted, which removed notice periods. Counting the top and bottom zones separately
  fixed it, and a regression test reproduces the exact page layout.
