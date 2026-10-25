# Policy engine check (E5, categories from gold)

LLM off. Clause categories come from the gold labels (draft); no classifier. Embeddings: off (semantic NEEDS_REVIEW step skipped). Targets: violation recall >= 85%, precision >= 80%.

| Measure | docx | text_pdf | scanned_pdf |
|---|---|---|---|
| **Violation recall** | 100.0% | 100.0% | 100.0% |
| **Violation precision** | 100.0% | 100.0% | 100.0% |
| Exact status accuracy | 100.0% | 100.0% | 100.0% |
| tp | 18 | 18 | 18 |
| fp | 0 | 0 | 0 |
| fn | 0 | 0 | 0 |
| failed_files | 0 | 0 | 0 |

## Confusion matrix: docx (rows gold, columns predicted)

| gold \ pred | NON_COMPLIANT | MISSING | NEEDS_REVIEW | COMPLIANT | NOT_APPLICABLE |
|---|---|---|---|---|---|
| NON_COMPLIANT | 14 | 0 | 0 | 0 | 0 |
| MISSING | 0 | 4 | 0 | 0 | 0 |
| NEEDS_REVIEW | 0 | 0 | 0 | 0 | 0 |
| COMPLIANT | 0 | 0 | 0 | 39 | 0 |
| NOT_APPLICABLE | 0 | 0 | 0 | 0 | 23 |

## Confusion matrix: text_pdf (rows gold, columns predicted)

| gold \ pred | NON_COMPLIANT | MISSING | NEEDS_REVIEW | COMPLIANT | NOT_APPLICABLE |
|---|---|---|---|---|---|
| NON_COMPLIANT | 14 | 0 | 0 | 0 | 0 |
| MISSING | 0 | 4 | 0 | 0 | 0 |
| NEEDS_REVIEW | 0 | 0 | 0 | 0 | 0 |
| COMPLIANT | 0 | 0 | 0 | 39 | 0 |
| NOT_APPLICABLE | 0 | 0 | 0 | 0 | 23 |

## Confusion matrix: scanned_pdf (rows gold, columns predicted)

| gold \ pred | NON_COMPLIANT | MISSING | NEEDS_REVIEW | COMPLIANT | NOT_APPLICABLE |
|---|---|---|---|---|---|
| NON_COMPLIANT | 14 | 0 | 0 | 0 | 0 |
| MISSING | 0 | 4 | 0 | 0 | 0 |
| NEEDS_REVIEW | 0 | 0 | 0 | 0 | 0 |
| COMPLIANT | 0 | 0 | 0 | 39 | 0 |
| NOT_APPLICABLE | 0 | 0 | 0 | 0 | 23 |

## Disagreements

None.
