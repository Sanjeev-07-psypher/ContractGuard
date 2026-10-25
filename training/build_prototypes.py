"""Category prototypes for the embedding fallback (HLD 6.4) and the tuned ``proto_threshold``.

Prototype = mean MiniLM embedding of up to 200 random training positives per category (seed 42),
L2-normalised. SLA has no training data: its prototype is the mean of the hand-written examples in
``patterns.yaml: sla_prototypes``.

Threshold: among validation rows the saved classifier leaves without a category, pick the value in
[0.30, 0.80] (step 0.05) that maximises fallback accuracy (a row is right if it gets one of its gold
categories, or stays OTHER when it has none). Copy the printed value into
``config/settings.yaml: embeddings.proto_threshold`` and docs/DECISIONS.md.

Outputs: models/prototypes.npy, models/prototypes.json (category order),
evaluation/results/prototype_threshold.json

Usage:
    python training/build_prototypes.py
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RESULTS, SEED, load_split  # noqa: E402

from contractguard.classification.classifier import artifact_paths, load_classifier  # noqa: E402
from contractguard.config import get_patterns, get_settings  # noqa: E402
from contractguard.embeddings.service import EmbeddingService, normalize_rows  # noqa: E402

PER_CATEGORY = 200
GRID = [round(0.3 + 0.05 * i, 2) for i in range(11)]


def main() -> int:
    settings = get_settings()
    embedder = EmbeddingService(settings=settings)
    clf = load_classifier(settings)
    train = load_split("train")
    rng = random.Random(SEED)

    cats, rows = [], []
    for cat in clf.categories:
        positives = [r["text"] for r in train if cat in r["labels"]]
        sample = rng.sample(positives, min(PER_CATEGORY, len(positives)))
        if sample:
            cats.append(cat)
            rows.append(embedder.encode(sample).mean(axis=0))
    cats.append("SLA")
    rows.append(embedder.encode(list(get_patterns()["sla_prototypes"])).mean(axis=0))
    matrix = normalize_rows(np.vstack(rows)).astype(np.float32)

    paths = artifact_paths(settings)
    np.save(paths["prototypes"], matrix)
    paths["prototype_categories"].write_text(json.dumps(cats) + "\n")

    val = load_split("val")
    P = clf.predict_proba([r["text"] for r in val])
    thr = np.array([clf.thresholds[c] for c in clf.categories])
    left = [r for r, p in zip(val, P, strict=True) if not np.any(p >= thr)]
    sims = (
        embedder.encode([r["text"] for r in left]) @ matrix.T if left else np.zeros((0, len(cats)))
    )
    results = {}
    for t in GRID:
        right = 0
        for r, s in zip(left, sims, strict=True):
            k = int(np.argmax(s))
            assigned = cats[k] if s[k] >= t else None
            right += (assigned in r["labels"]) if assigned else (not r["labels"])
        results[t] = round(right / len(left), 4) if left else None
    best = max(GRID, key=lambda t: (results[t] or 0, t))
    out = {
        "categories": cats,
        "fallback_rows": len(left),
        "accuracy_by_threshold": results,
        "best_threshold": best,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "prototype_threshold.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))
    print(f"\nSet embeddings.proto_threshold: {best} in config/settings.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
