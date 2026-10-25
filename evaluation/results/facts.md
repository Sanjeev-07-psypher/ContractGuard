# Fact extraction check (Phase 5)

E4 target: fact exact-match accuracy >= 85%. Clause categories come from the gold labels (no classifier yet), and the gold labels are still a DRAFT.

| Measure | docx | text_pdf | scanned_pdf |
|---|---|---|---|
| **All facts (E4)** | 100.0% | 100.0% | 100.0% |
| Facts with a non-null gold value | 100.0% | 100.0% | 100.0% |
| `termination.notice_days` | 100.0% | 100.0% | 100.0% |
| `termination.counterparty_unilateral` | 100.0% | 100.0% | 100.0% |
| `liability.has_cap` | 100.0% | 100.0% | 100.0% |
| `liability.is_uncapped` | 100.0% | 100.0% | 100.0% |
| `renewal.is_automatic` | 100.0% | 100.0% | 100.0% |
| `payment.due_days` | 100.0% | 100.0% | 100.0% |
| `governing_law.jurisdiction` | 100.0% | 100.0% | 100.0% |
| meta `parties` | 100.0% | 100.0% | 100.0% |
| meta `effective_date` | 100.0% | 100.0% | 100.0% |
| meta `expiry_date` | 100.0% | 100.0% | 100.0% |
| meta `governing_law` | 100.0% | 100.0% | 100.0% |
| meta `contract_type` | 100.0% | 100.0% | 100.0% |
| Failed files | 0 | 0 | 0 |

## Errors

None.
