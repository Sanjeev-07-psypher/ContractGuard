# Label agreement: draft vs labeller_ai

| Measure | Agreement |
|---|---|
| Clause boundaries (F1 on clause identities) | 1.0 |
| Clause categories, exact set match | 141/145 (97.2%) |
| Facts (exact) | 54/56 (96.4%) |
| Metadata: dates, governing law, type (exact) | 32/32 (100.0%) |
| Rule statuses (exact) | 80/80 (100.0%) |

Cohen's kappa per category, pooled over matched clauses (— = only one value used, undefined):

| Category | Kappa |
|---|---|
| CONFIDENTIALITY | 0.898 |
| TERMINATION | 0.93 |
| PAYMENT | 1.0 |
| LIABILITY | 1.0 |
| INDEMNIFICATION | 1.0 |
| IP | 1.0 |
| GOVERNING_LAW | 1.0 |
| RENEWAL | 1.0 |
| SLA | 1.0 |
| OTHER | 0.967 |

## Disagreements

| Contract | Item | Draft | Second |
|---|---|---|---|
| gc02 | rule R02 evidence | ['11.1', '11.2', '11.3'] | ['11.1'] |
| gc06 | categories 8 | ['TERMINATION'] | ['CONFIDENTIALITY', 'TERMINATION'] |
| gc06 | rule R07 evidence | ['2', '3'] | ['3'] |
| gc07 | categories I | ['OTHER'] | ['CONFIDENTIALITY'] |
| gc07 | categories VII | ['RENEWAL', 'TERMINATION'] | ['CONFIDENTIALITY', 'RENEWAL'] |
| gc07 | fact termination.notice_days | 30 | None |
| gc07 | fact termination.counterparty_unilateral | False | None |
| gc08 | categories 11 | ['OTHER'] | ['TERMINATION'] |
