# 05 Clause classification and embeddings

Files: `contractguard/classification/classifier.py`, `features.py`,
`contractguard/embeddings/service.py`; artifacts in `models/`.

## What

Gives each `BODY` and `EXHIBIT` clause zero or more categories from `CONFIDENTIALITY`,
`TERMINATION`, `PAYMENT`, `LIABILITY`, `INDEMNIFICATION`, `IP`, `GOVERNING_LAW`, `RENEWAL`, `SLA`
and `OTHER`, with a score per category and a note of how it was decided (`classified_by`).

## Why

The policy engine asks "is there a liability clause, and what does it say?". Fact extractors only
read clauses of their own category, which keeps them precise: a "30 days" in a payment clause must
not be read as a notice period. Clauses can belong to several categories (a termination clause
that also covers confidentiality after termination), so this is **multi-label** classification.

## How

For each classifiable clause, `ClauseClassifier.classify`:

1. **Trained classifier.** `predict_proba` from the saved scikit-learn pipeline (TF-IDF features
   and a calibrated linear SVM per category). A category is assigned when its probability reaches
   that category's tuned threshold (`models/thresholds.json`, between 0.3 for RENEWAL and 0.8 for
   INDEMNIFICATION).
2. **SLA keyword rule.** Neither training dataset labels service levels, so a clause matching
   `patterns.yaml: sla_keywords` ("service level", "SLA", uptime wording) gets `SLA`. If the
   classifier found nothing else, `classified_by` becomes `rule`.
3. **Embedding fallback.** A clause still without a category is embedded with MiniLM and compared
   with one prototype vector per category (the mean embedding of up to 200 training examples). If
   the best cosine similarity is at least `embeddings.proto_threshold` (0.80, D50), that category is
   assigned with `low_confidence=True` and `classified_by="embedding_fallback"`. The policy engine
   turns findings based only on low-confidence clauses into NEEDS_REVIEW.
4. Otherwise the clause is `OTHER`.

`PREAMBLE`, `DEFINITIONS` and `SIGNATURE` clauses are not classified.

### `features.py`

Code that must be importable when the pickled model loads:

- `legal_stop_words()`: scikit-learn's English stop words **minus** negations ("no", "not", "nor",
  "never", "none", "without", "unless", "except", "notwithstanding").
- `MaskedOneVsRest` (D39): one binary classifier per category, trained only on rows where that
  category's label is known. LEDGAR has no LIABILITY or RENEWAL label and CUAD has no
  CONFIDENTIALITY, PAYMENT or INDEMNIFICATION label; a CUAD paragraph about confidentiality is
  therefore *unknown* (-1) for CONFIDENTIALITY, not a negative example. Without masks the model
  learned that TERMINATION never happens in CUAD-style text.
- `MiniLMEncoder`: a scikit-learn transformer wrapping the embedding model, used by the MiniLM
  comparison model.

### `embeddings/service.py`

- `EmbeddingService`: lazy, thread-safe wrapper around `SentenceTransformer`
  (`sentence-transformers/all-MiniLM-L6-v2`, 384 dimensions) on CPU. It tries the local cache first,
  so no network call happens once the model is downloaded. Vectors are L2-normalised, so cosine
  similarity is a dot product.
- `cosine_top_k(query, matrix, k)`: a NumPy matrix product and a stable sort; no vector database.
- `try_load_embedder`: returns `None` instead of failing; the pipeline then adds a warning and
  skips the semantic steps.

## Callers and dependencies

`pipeline.Resources.load` calls `load_classifier(settings, embedder)`; `pipeline.run` calls
`classify`. The policy engine reuses the embedder for its semantic search. Depends on
scikit-learn, joblib, NumPy and sentence-transformers (PyTorch).

## Data in and out

In: `list[Clause]` from segmentation. Out: the same clauses with `categories`, `scores`,
`low_confidence` and `classified_by` filled.

## Errors and edge cases

- Missing `classifier.joblib` or `thresholds.json`: `ModelArtifactError`, and the run stops.
  Without a classifier every required clause would be reported MISSING, a confidently wrong report
  (D32).
- Missing prototypes or embedding model: the fallback is skipped, with a warning.
- The pickled model must be loaded with the same scikit-learn version that saved it (pinned in
  `deploy/requirements.txt`).

## Configuration

`classification.model_path`, `thresholds_path`, `embeddings.model_name`, `proto_threshold`,
`prototypes_path` in `settings.yaml`; `sla_keywords` and `sla_prototypes` in `patterns.yaml`.

## Alternatives considered

Five models were compared on the validation split (macro-F1 at threshold 0.5):

| Model | Best validation macro-F1 |
|---|---|
| TF-IDF + calibrated linear SVM (C = 1) | **0.857** (selected; 0.875 with tuned thresholds) |
| TF-IDF + logistic regression (C = 64) | 0.846 |
| TF-IDF + random forest | 0.815 |
| TF-IDF + multinomial naive Bayes | 0.716 |
| MiniLM embeddings + logistic regression | 0.607 |

Fine-tuning a transformer (Legal-BERT) was out of scope: no GPU, slower inference, and the linear
model already beats the 0.75 target.

## Interview notes

- *Result on the test split (E1)?* Macro-F1 0.854, micro-F1 0.869 over 10,399 test rows. Weakest
  categories: TERMINATION (F1 0.73) and PAYMENT (0.76); most errors are missed labels (predicted
  "none"), not confusions between categories.
- *Why does the SVM need calibration?* A linear SVM outputs distances, not probabilities.
  `CalibratedClassifierCV` with sigmoid (Platt) scaling and 3-fold cross-validation turns them into
  probabilities, so per-category thresholds mean something.
- *Why per-category thresholds?* Categories differ in frequency and difficulty. Each threshold is
  the value in 0.2 to 0.8 (step 0.05) with the best validation F1 for that category.
- *Why did MiniLM lose?* Its general-purpose sentence embeddings blur legal distinctions that
  specific words and bigrams capture ("limitation of liability", "governed by"), and a linear model
  on 384 dense features has less to work with than on 100,000 sparse ones.
- *Why keep negations out of the stop-word list?* "shall not be liable" and "shall be liable" must
  not look the same.
