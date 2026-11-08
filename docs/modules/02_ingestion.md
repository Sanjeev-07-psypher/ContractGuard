# 02 Ingestion and OCR

Files: `contractguard/ingestion/router.py`, `pdf_loader.py`, `ocr.py`, `docx_loader.py`.

## What

Turns an uploaded file into a `Document`: an ordered list of text `Block`s, each knowing its page
(PDF) or paragraph index (DOCX), whether it came from OCR, and its OCR confidence.

## Why

Contracts arrive as digital PDFs, scanned PDFs and Word files. Everything after this stage should
work on plain text with a map back to where it came from, whatever the format. Scans are common in
Indian procurement, so OCR is a first-class path, not an afterthought.

## How

### `router.py`: validate and dispatch

1. `detect_file_type(path)`: the extension must be `.pdf` or `.docx`, **and** the first bytes must
   match: `%PDF` for PDF, `PK\x03\x04` (a ZIP archive) for DOCX. A renamed `.exe` is rejected.
2. `check_size`: at most `limits.max_file_mb` (20 MB).
3. Load with the PDF or DOCX loader.
4. If no block has any text, raise `EMPTY_DOCUMENT`.

### `pdf_loader.py`: text first, OCR only where needed

For each page:

1. Read text blocks with PyMuPDF (`page.get_text("blocks")`), keep text blocks only, and sort them
   top to bottom, then left to right.
2. `is_scanned`: the page is scanned if it has fewer than `ocr.min_chars_per_page` (50) characters
   **and** contains an image. Only those pages go to OCR, so a PDF that mixes typed pages and a
   scanned signature page works page by page.
3. Scanned page: `ocr_fn(page)` returns paragraphs and a mean confidence. Below
   `ocr.warn_confidence` (70), the document gets a warning such as
   "Page 3 OCR confidence 62% - verify manually".

Limits: encrypted PDFs (`ENCRYPTED_PDF`) and more than `limits.max_pages` (60) pages
(`TOO_MANY_PAGES`) are rejected; a file PyMuPDF cannot open is `CORRUPT_FILE`.

### `ocr.py`: Tesseract

1. `render_page`: render the page with PyMuPDF at `ocr.dpi` (300) in grayscale. No poppler needed.
2. `ocr_image`: `pytesseract.image_to_data` with `--oem 1 --psm 6` (LSTM engine, one uniform block
   of text). Words are grouped back into lines and paragraphs using Tesseract's block, paragraph
   and line numbers, so the paragraph structure survives.
3. Confidence = mean of word confidences above 0.
4. `tesseract_available()` is cached and always resets pytesseract's command first, so a custom
   path from one call never leaks into the next (a bug found by a test).

### `docx_loader.py`: rebuild Word's automatic numbering

Word stores "7.2" outside the paragraph text, in the numbering definitions. Without them, the
segmenter would see a heading with no number.

1. `Numbering.from_document` reads `numbering.xml`: for each list, each level's start value,
   format (decimal, letters, roman) and label template such as `%1.%2`.
2. For each numbered paragraph (`w:numPr` on the paragraph or inherited from its style),
   `Numbering.label` advances that level's counter, resets deeper levels, and renders the label.
3. Paragraphs and tables are read in document order. A table row becomes one block with cells
   joined by ` | ` (merged cells are de-duplicated).
4. Each block keeps its Word style name (for example "Heading 2") as a hint for segmentation.
5. More than `limits.max_docx_words` (60,000) words raises `TOO_MANY_WORDS`.

DOCX has no pages, so `page` stays `None`; findings in DOCX contracts are located by section.

## Callers and dependencies

Called by `pipeline.run` through `load_document`. Uses PyMuPDF, pytesseract with the Tesseract 5
binary, Pillow and python-docx.

## Data in and out

In: a file path and `Settings`. Out: `Document(file_type, num_pages, blocks, ocr_pages, warnings)`.

## Errors and edge cases

| Situation | Result |
|---|---|
| Wrong extension or content does not match it | `UNSUPPORTED_FILE_TYPE` |
| Password-protected PDF | `ENCRYPTED_PDF` |
| Scanned page but Tesseract missing | `OCR_UNAVAILABLE` with install instructions |
| Low OCR confidence | warning in the report, analysis continues |
| Two-column layouts | blocks are sorted by position; columns can interleave (known limit) |

## Configuration

`limits.*` and `ocr.*` in `settings.yaml`; `CG_OCR__TESSERACT_CMD` for a custom Tesseract path
(common on Windows).

## Alternatives considered

- **pdfplumber or pdfminer**: slower, and no page rendering for OCR. PyMuPDF does both.
- **OCR every page**: slower and less accurate than reading the embedded text of digital pages.
- **Cloud OCR (Google Vision, AWS Textract)**: more accurate, but sends whole contracts off the
  machine and costs money. Tesseract runs locally for free.
- **docx2txt**: loses automatic numbering, which segmentation depends on.

## Interview notes

- *How do you detect a scanned page?* Less than 50 characters of extractable text plus an image on
  the page. Checked per page, not per document.
- *What do `--oem 1 --psm 6` mean?* OCR engine mode 1 is the LSTM neural engine; page segmentation
  mode 6 treats the page as one uniform block of text, which suits contract pages.
- *Why render at 300 DPI?* Tesseract is most accurate around 300 DPI; lower loses small fonts,
  higher costs time without gains.
- *Measured OCR quality?* Character error rate 1.10% on the simulated scans of the 8 gold
  contracts. Simulated scans are cleaner than real ones, so this is optimistic (D16).
- *Why check magic bytes?* The extension is user-controlled; the first bytes are what parsers act
  on. It stops renamed files reaching the wrong parser.
