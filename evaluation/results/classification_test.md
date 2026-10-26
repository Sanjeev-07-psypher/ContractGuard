# Clause classification on the test split (E1, model linear_svc)

Target: macro-F1 >= 0.75. Tuned per-class thresholds. Scores are masked by source coverage (D39).

| Split | Rows | Macro-F1 | Micro-F1 |
|---|---|---|---|
| all | 10399 | 0.8544 | 0.8691 |
| cuad | 399 | 0.5121 | 0.8261 |
| ledgar | 10000 | 0.6409 | 0.8734 |

| Category | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| CONFIDENTIALITY | 0.8667 | 0.9341 | 0.8991 | 167 |
| TERMINATION | 0.7113 | 0.7426 | 0.7266 | 136 |
| PAYMENT | 0.7008 | 0.8279 | 0.7591 | 215 |
| LIABILITY | 0.9574 | 0.7627 | 0.8491 | 59 |
| INDEMNIFICATION | 0.9135 | 0.9337 | 0.9235 | 181 |
| IP | 0.8736 | 0.8539 | 0.8636 | 89 |
| GOVERNING_LAW | 0.8818 | 0.9567 | 0.9178 | 624 |
| RENEWAL | 0.9286 | 0.8667 | 0.8966 | 15 |

## Confusion matrix (rows gold, columns predicted)

| gold \ pred | CONFIDENTIALITY | TERMINATION | PAYMENT | LIABILITY | INDEMNIFICATION | IP | GOVERNING_LAW | RENEWAL | NONE |
|---|---|---|---|---|---|---|---|---|---|
| CONFIDENTIALITY | 156 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 11 |
| TERMINATION | 0 | 99 | 0 | 0 | 0 | 0 | 0 | 0 | 33 |
| PAYMENT | 0 | 0 | 178 | 0 | 0 | 0 | 0 | 0 | 37 |
| LIABILITY | 1 | 0 | 1 | 39 | 2 | 1 | 0 | 0 | 10 |
| INDEMNIFICATION | 0 | 0 | 1 | 2 | 168 | 0 | 0 | 0 | 10 |
| IP | 1 | 0 | 0 | 0 | 0 | 75 | 0 | 0 | 10 |
| GOVERNING_LAW | 0 | 0 | 0 | 1 | 0 | 0 | 595 | 0 | 22 |
| RENEWAL | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 11 | 0 |
