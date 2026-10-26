# Training the clause classifier

This folder turns two public datasets into the clause classifier that the pipeline loads from
`models/` (HLD §6.4). The gold contracts in `evaluation/gold/` are never used here.

## Steps

| Step | Script | Output |
|---|---|---|
| 1. Check label names | `inspect_labels.py` | `docs/labels_ledgar.txt`, `docs/labels_cuad.txt`; flags any name in `config/label_map.yaml` the datasets do not have |
| 2. CUAD examples | `prepare_cuad.py` | `data/processed/cuad_{train,val,test}.jsonl` |
| 3. LEDGAR examples | `prepare_ledgar.py` | `data/processed/ledgar_{train,val,test}.jsonl` |
| 4. Train and compare | `train_classifier.py` | `models/classifier.joblib`, `models/thresholds.json`, `evaluation/results/classification_models.*` |
| 5. Test (E1) | `evaluate.py` | `evaluation/results/classification_test.*`, `classification_confusion.png` |
| 6. Prototypes | `build_prototypes.py` | `models/prototypes.{npy,json}`, `evaluation/results/prototype_threshold.json` |

CUAD comes from GitHub (`TheAtticusProject/cuad`, `data.zip`, unzipped into `data/raw/cuad/`).
LEDGAR comes from Hugging Face (`coastalcph/lex_glue`, config `ledgar`). The MiniLM model
(`sentence-transformers/all-MiniLM-L6-v2`) is downloaded on first use. If your network blocks
Hugging Face file downloads, allow `huggingface.co`, `*.hf.co` and `*.xethub.hf.co`.

## Data

**CUAD** (510 contracts, 41 annotated categories). For every annotation of a mapped category,
the paragraph that contains it (paragraphs are split on blank lines) becomes a positive example.
Up to 5 paragraphs per contract with no mapped annotation become negatives. The split is by
contract (GroupShuffleSplit 80/10/10, seed 42), so no contract appears in two splits.

**LEDGAR** (provisions from SEC filings, 100 labels, one per provision). Mapped labels become a
category; the rest become OTHER. OTHER is downsampled to 3× the largest positive class in the
train split only (D40). LexGLUE's official splits are kept.

Every row has `text`, `labels` (a list, empty for OTHER), `source` and `group_id`.

## Label masks (D39)

The two datasets do not label the same things:

| Category | LEDGAR | CUAD |
|---|---|---|
| CONFIDENTIALITY, PAYMENT, INDEMNIFICATION | labelled | not labelled at all |
| TERMINATION, IP | labelled | only narrow labels (termination for convenience, IP assignment) |
| LIABILITY | no label | labelled (cap on liability, uncapped liability) |
| GOVERNING_LAW | labelled | labelled |
| RENEWAL | no label | labelled |

A CUAD paragraph about confidentiality is therefore *not* a negative example for
CONFIDENTIALITY; its label for that category is unknown. Each training row gets, per category,
1 (positive), 0 (true negative) or -1 (unknown). `MaskedOneVsRest` trains one binary model per
category on the rows where that category is known, and scores are computed the same way.
`config/label_map.yaml: cuad_negatives` lists the categories for which CUAD negatives count.

Without masks the CUAD-only smoke test showed the failure clearly: with no negatives for
TERMINATION and IP, the model predicted them for every paragraph.

## Models and selection

All five models share one interface (a scikit-learn `Pipeline` of features and a
`MaskedOneVsRest` classifier), so the rest of the system does not care which one wins.

| Name | Features | Classifier | Tuned on validation |
|---|---|---|---|
| `naive_bayes` | TF-IDF | MultinomialNB | alpha |
| `logreg` | TF-IDF | LogisticRegression (balanced) | C |
| `linear_svc` | TF-IDF | LinearSVC + sigmoid calibration | C |
| `random_forest` | TF-IDF | RandomForest (balanced) | none |
| `minilm_logreg` | MiniLM embeddings | LogisticRegression (balanced) | C |

TF-IDF uses word 1-2 grams, `min_df=2`, `max_df=0.9`, sublinear TF, and sklearn's English stop
words **minus** negation words (`not`, `no`, `unless`, `except`, `notwithstanding`, ...), because
negation changes legal meaning. Features are fitted on the train split only.

The model with the best validation macro-F1 at threshold 0.5 is saved. Then each category gets
the threshold in [0.20, 0.80] (step 0.05) with the best validation F1.

## Interview notes

- *Why TF-IDF + linear models instead of a fine-tuned transformer?* CPU-only, fast, explainable
  (feature weights), and strong on clause topics; Legal-BERT is a stretch goal (HLD §1.2).
- *Why tune thresholds per class?* Classes have very different base rates; one global 0.5 cut
  favours frequent classes.
- *Why calibrate LinearSVC?* Thresholds and the policy engine need probabilities, which an SVM
  does not give by itself.
- *Why split CUAD by contract?* Paragraphs from one contract share wording; a random split would
  leak and inflate scores.
