# Clause classifier comparison (validation)

Sources: cuad, ledgar. Train rows 21180, validation rows 10418. Macro-F1 over 8 categories at threshold 0.5, masked by source coverage (D39).

| Model | Params | Val macro-F1 | Fit (s) | Status |
|---|---|---|---|---|
| naive_bayes | {'alpha': 0.03} | 0.7158 | 0.3 | ok |
| naive_bayes | {'alpha': 0.1} | 0.6996 | 0.2 | ok |
| naive_bayes | {'alpha': 0.3} | 0.6943 | 0.3 | ok |
| naive_bayes | {'alpha': 1.0} | 0.4797 | 0.1 | ok |
| logreg | {'C': 1.0} | 0.7812 | 7.6 | ok |
| logreg | {'C': 4.0} | 0.8165 | 9.8 | ok |
| logreg | {'C': 16.0} | 0.8428 | 13.3 | ok |
| logreg | {'C': 64.0} | 0.8457 | 13.1 | ok |
| linear_svc | {'C': 0.1} | 0.8303 | 2.6 | ok |
| linear_svc | {'C': 0.3} | 0.8492 | 3.5 | ok |
| linear_svc | {'C': 1.0} | 0.8569 | 5.2 | ok |
| random_forest | {'n_estimators': 200, 'min_samples_leaf': 2} | 0.8149 | 42.7 | ok |
| minilm_logreg | {'C': 1.0} | 0.5668 | 3.3 | ok |
| minilm_logreg | {'C': 4.0} | 0.5901 | 4.5 | ok |
| minilm_logreg | {'C': 16.0} | 0.6067 | 5.7 | ok |

Selected: **linear_svc** {'C': 1.0}; validation macro-F1 0.8569 at 0.5, 0.875 with tuned thresholds.

| Category | Threshold |
|---|---|
| CONFIDENTIALITY | 0.75 |
| TERMINATION | 0.7 |
| PAYMENT | 0.65 |
| LIABILITY | 0.75 |
| INDEMNIFICATION | 0.8 |
| IP | 0.7 |
| GOVERNING_LAW | 0.6 |
| RENEWAL | 0.3 |
