# End-to-end evaluation on the gold set (E3, E5, E6, E8)

Full pipeline with the trained classifier, LLM off. Gold labels are still a draft (see evaluation/gold/ADJUDICATION.md).

| Measure | Target | docx | text_pdf | scanned_pdf |
|---|---|---|---|---|
| E5 violation recall | >= 85% | 88.9% | 88.9% | 88.9% |
| E5 violation precision | >= 80% | 100.0% | 100.0% | 100.0% |
| E5 exact status accuracy |  | 93.8% | 93.8% | 93.8% |
| E6 Precision@3 | >= 70% | 35.2% | 35.2% | 35.2% |
| E6 Recall@3 |  | 96.5% | 96.5% | 96.5% |
| E6 MRR |  | 90.9% | 90.9% | 90.9% |
| E8 seconds per contract (mean) | < 30 s | 0.26 | 0.2 | 7.19 |
| E8 seconds per contract (max) |  | 0.7 | 0.6 | 10.6 |
| Failed files | 0 | 0 | 0 | 0 |

E3 status agreement, text PDF vs scanned PDF: **100.0%** (target >= 90%).

## E5 confusion matrix: docx (rows gold, columns predicted)

| gold \ pred | NON_COMPLIANT | MISSING | NEEDS_REVIEW | COMPLIANT | NOT_APPLICABLE |
|---|---|---|---|---|---|
| NON_COMPLIANT | 14 | 0 | 0 | 0 | 0 |
| MISSING | 0 | 2 | 2 | 0 | 0 |
| NEEDS_REVIEW | 0 | 0 | 0 | 0 | 0 |
| COMPLIANT | 0 | 0 | 0 | 38 | 1 |
| NOT_APPLICABLE | 0 | 0 | 2 | 0 | 21 |

## E5 confusion matrix: text_pdf (rows gold, columns predicted)

| gold \ pred | NON_COMPLIANT | MISSING | NEEDS_REVIEW | COMPLIANT | NOT_APPLICABLE |
|---|---|---|---|---|---|
| NON_COMPLIANT | 14 | 0 | 0 | 0 | 0 |
| MISSING | 0 | 2 | 2 | 0 | 0 |
| NEEDS_REVIEW | 0 | 0 | 0 | 0 | 0 |
| COMPLIANT | 0 | 0 | 0 | 38 | 1 |
| NOT_APPLICABLE | 0 | 0 | 2 | 0 | 21 |

## E5 confusion matrix: scanned_pdf (rows gold, columns predicted)

| gold \ pred | NON_COMPLIANT | MISSING | NEEDS_REVIEW | COMPLIANT | NOT_APPLICABLE |
|---|---|---|---|---|---|
| NON_COMPLIANT | 14 | 0 | 0 | 0 | 0 |
| MISSING | 0 | 2 | 2 | 0 | 0 |
| NEEDS_REVIEW | 0 | 0 | 0 | 0 | 0 |
| COMPLIANT | 0 | 0 | 0 | 38 | 1 |
| NOT_APPLICABLE | 0 | 0 | 2 | 0 | 21 |

## Disagreements

| Contract | Format | Rule | Gold | Predicted |
|---|---|---|---|---|
| gc03 | docx | R05 | NOT_APPLICABLE | NEEDS_REVIEW |
| gc03 | docx | R06 | MISSING | NEEDS_REVIEW |
| gc03 | docx | R10 | MISSING | NEEDS_REVIEW |
| gc03 | text_pdf | R05 | NOT_APPLICABLE | NEEDS_REVIEW |
| gc03 | text_pdf | R06 | MISSING | NEEDS_REVIEW |
| gc03 | text_pdf | R10 | MISSING | NEEDS_REVIEW |
| gc03 | scanned_pdf | R05 | NOT_APPLICABLE | NEEDS_REVIEW |
| gc03 | scanned_pdf | R06 | MISSING | NEEDS_REVIEW |
| gc03 | scanned_pdf | R10 | MISSING | NEEDS_REVIEW |
| gc06 | docx | R05 | NOT_APPLICABLE | NEEDS_REVIEW |
| gc06 | text_pdf | R05 | NOT_APPLICABLE | NEEDS_REVIEW |
| gc06 | scanned_pdf | R05 | NOT_APPLICABLE | NEEDS_REVIEW |
| gc08 | docx | R05 | COMPLIANT | NOT_APPLICABLE |
| gc08 | text_pdf | R05 | COMPLIANT | NOT_APPLICABLE |
| gc08 | scanned_pdf | R05 | COMPLIANT | NOT_APPLICABLE |
