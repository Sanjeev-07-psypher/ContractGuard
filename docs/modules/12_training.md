# 12 Training the classifier

Files: `training/inspect_labels.py`, `prepare_cuad.py`, `prepare_ledgar.py`, `train_classifier.py`,
`evaluate.py`, `build_prototypes.py`, `common.py`; mapping in `config/label_map.yaml`; outputs in
`models/` and `evaluation/results/`. Step-by-step instructions: [`training/README.md`](../../training/README.md).

## What

Offline scripts that turn two public datasets into the clause classifier, its per-category
thresholds and the category prototypes that the pipeline loads at runtime.

## Why

There is no labelled set of Indian contract clauses. Two public English datasets cover most of the
needed categories: **LEDGAR** (provisions from SEC filings, 100 labels, one per provision; from the
LexGLUE benchmark) and **CUAD** (510 contracts annotated by lawyers for 41 clause types). The
8 gold contracts are never used for training or tuning; they are the final exam.

## How

| Step | Script | Output |
|---|---|---|
| 1 | `inspect_labels.py`: prints every label of both datasets and checks every name in `label_map.yaml` exists | `docs/labels_ledgar.txt`, `docs/labels_cuad.txt` |
| 2 | `prepare_cuad.py`: the paragraph containing each mapped annotation is a positive; up to 5 unannotated paragraphs per contract are negatives; split by contract 80/10/10 (GroupShuffleSplit, seed 42) | `data/processed/cuad_{train,val,test}.jsonl` |
| 3 | `prepare_ledgar.py`: mapped labels become categories, the rest OTHER; OTHER downsampled to 3 times the largest class in train only (D40); official splits kept | `data/processed/ledgar_*.jsonl` |
| 4 | `train_classifier.py`: fit the vectoriser on train only, try 5 model families over small grids, choose by validation macro-F1, tune per-category thresholds | `models/classifier.joblib`, `models/thresholds.json`, comparison table |
| 5 | `evaluate.py`: test-split scores (E1), per source, confusion matrix | `classification_test.*`, `classification_confusion.png` |
| 6 | `build_prototypes.py`: mean MiniLM embedding of up to 200 training positives per category (SLA from hand-written examples); tune the fallback threshold on validation | `models/prototypes.npy`, `prototypes.json` |

**Label masks (D39).** Each row gets, per category, 1 (positive), 0 (true negative) or -1
(unknown, because that row's dataset never labels that category). `MaskedOneVsRest` trains each
category only on rows where it is known.

**Features.** TF-IDF on words and bigrams, `min_df=2`, `max_df=0.9`, sublinear term frequency,
lowercase, stop words without negations.

**Leakage control.** The saved artifact is one scikit-learn `Pipeline(vectoriser, classifier)`
fitted on the training split only; CUAD is split by contract, so paragraphs of one contract never
appear in two splits.

## Results (run on 2026-10-26)

- Train rows 21,180, validation rows 10,418, test rows 10,399.
- Selected: TF-IDF + calibrated linear SVM, C = 1. Validation macro-F1 0.857 at 0.5, 0.875 with tuned
  thresholds. Test macro-F1 **0.854**, micro-F1 0.869 (target 0.75).
- Fallback threshold 0.80 (D50).

## Errors and edge cases

- If Hugging Face downloads are blocked, LEDGAR and MiniLM cannot be fetched; CUAD downloads from
  GitHub. The MiniLM comparison model is skipped when MiniLM is unavailable.
- The pickled model depends on the scikit-learn version; it is pinned for deployment.

## Alternatives considered

- **Train on the gold contracts**: there are only 8 and they are the test set. Rejected.
- **Fine-tune Legal-BERT**: likely a few points better, but needs a GPU and slows inference;
  the linear model already exceeds the target.
- **Use only CUAD**: too few examples for several categories, and no confidentiality or payment
  labels.

## Interview notes

- *What is LEDGAR?* About 80,000 contract provisions from SEC EDGAR filings, each labelled by its
  heading, used as a LexGLUE benchmark task.
- *What is CUAD?* The Contract Understanding Atticus Dataset: 510 commercial contracts with more
  than 13,000 lawyer annotations over 41 categories.
- *How did you handle class imbalance?* Balanced class weights, downsampling OTHER in training,
  per-category thresholds, and macro-F1 for selection so rare categories count equally.
- *Why macro-F1?* Micro-F1 is dominated by frequent categories such as governing law; macro-F1
  shows whether rare ones such as renewal work.
