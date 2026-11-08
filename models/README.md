# models/

Trained artifacts written by `training/` (Phase 4). They are committed so the Docker image and the
Hugging Face Space can run without retraining (D53).

- `classifier.joblib`: best sklearn pipeline by validation macro-F1 (linear SVC), xz-compressed
- `thresholds.json`: per-category probability thresholds
- `prototypes.npy`, `prototypes.json`: per-category mean MiniLM embeddings and their category names

Retraining (see `training/README.md`) overwrites them. `scikit-learn` must stay at the version in
`deploy/requirements.txt`, or the pickled pipeline may not load.
