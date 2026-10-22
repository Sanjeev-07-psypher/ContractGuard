# models/

Trained artifacts are written here by `training/` (Phase 4) and are not committed:

- `classifier.joblib`: best sklearn pipeline by validation macro-F1
- `thresholds.json`: per-category probability thresholds
- `prototypes.npy`: per-category mean MiniLM embeddings
