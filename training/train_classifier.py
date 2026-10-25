"""Train and compare clause classifiers, tune per-class thresholds, save the best (HLD 6.4).

Models (all multi-label one-vs-rest with label masks, D39):
    naive_bayes    TF-IDF + MultinomialNB            (alpha tuned)
    logreg         TF-IDF + LogisticRegression       (C tuned, class_weight=balanced)
    linear_svc     TF-IDF + calibrated LinearSVC     (C tuned)
    random_forest  TF-IDF + RandomForest
    minilm_logreg  MiniLM embeddings + LogisticRegression (C tuned; skipped if MiniLM unavailable)

The vectorizer (or encoder) is fitted on the training split only, then reused across the grid; the
saved artifact is an sklearn ``Pipeline(vectorizer, classifier)``, so there is no leakage.
Selection: macro-F1 on validation at threshold 0.5. Then, for the chosen model, each category's
threshold is the value in [0.2, 0.8] (step 0.05) with the best validation F1.

Outputs: models/classifier.joblib, models/thresholds.json,
evaluation/results/classification_models.{json,md} (the comparison table).

Usage:
    python training/train_classifier.py [--sources ledgar cuad] [--models logreg ...]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RESULTS, SEED, label_matrix, load_split, trained_categories  # noqa: E402

from contractguard.classification.features import (  # noqa: E402
    MaskedOneVsRest,
    MiniLMEncoder,
    legal_stop_words,
)
from contractguard.config import get_settings  # noqa: E402

THRESHOLD_GRID = [round(0.2 + 0.05 * i, 2) for i in range(13)]  # 0.20 .. 0.80


def tfidf() -> TfidfVectorizer:
    return TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.9,
        sublinear_tf=True,
        lowercase=True,
        stop_words=legal_stop_words(),
    )


def candidates() -> dict[str, tuple[str, list[tuple[dict, Any]]]]:
    """name -> (feature kind, [(params, unfitted classifier), ...])."""
    lr = lambda c: LogisticRegression(C=c, class_weight="balanced", max_iter=2000)  # noqa: E731
    svc = lambda c: CalibratedClassifierCV(  # noqa: E731
        LinearSVC(C=c, class_weight="balanced"), cv=3, method="sigmoid"
    )
    rf = RandomForestClassifier(
        n_estimators=200,
        class_weight="balanced_subsample",
        min_samples_leaf=2,
        n_jobs=-1,
        random_state=SEED,
    )
    return {
        "naive_bayes": (
            "tfidf",
            [({"alpha": a}, MultinomialNB(alpha=a)) for a in (0.03, 0.1, 0.3, 1.0)],
        ),
        "logreg": ("tfidf", [({"C": c}, lr(c)) for c in (1.0, 4.0, 16.0, 64.0)]),
        "linear_svc": ("tfidf", [({"C": c}, svc(c)) for c in (0.1, 0.3, 1.0)]),
        "random_forest": ("tfidf", [({"n_estimators": 200, "min_samples_leaf": 2}, rf)]),
        "minilm_logreg": ("minilm", [({"C": c}, lr(c)) for c in (1.0, 4.0, 16.0)]),
    }


def per_class_f1(Y: np.ndarray, P: np.ndarray, thresholds: list[float]) -> list[dict]:
    """Masked P/R/F1 per column; rows with Y == -1 are ignored for that column."""
    out = []
    for k in range(Y.shape[1]):
        known = Y[:, k] != -1
        y, p = Y[known, k], P[known, k] >= thresholds[k]
        tp, fp, fn = (
            int(np.sum(p & (y == 1))),
            int(np.sum(p & (y == 0))),
            int(np.sum(~p & (y == 1))),
        )
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        out.append(
            {
                "precision": prec,
                "recall": rec,
                "f1": f1,
                "support": int(np.sum(y == 1)),
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "n": int(known.sum()),
            }
        )
    return out


def macro_f1(Y: np.ndarray, P: np.ndarray, thresholds: list[float] | None = None) -> float:
    thresholds = thresholds or [0.5] * Y.shape[1]
    return float(np.mean([c["f1"] for c in per_class_f1(Y, P, thresholds)]))


def micro_f1(Y: np.ndarray, P: np.ndarray, thresholds: list[float]) -> float:
    stats = per_class_f1(Y, P, thresholds)
    tp, fp, fn = (sum(c[k] for c in stats) for k in ("tp", "fp", "fn"))
    return 2 * tp / (2 * tp + fp + fn) if tp else 0.0


def tune_thresholds(Y: np.ndarray, P: np.ndarray) -> list[float]:
    best = []
    for k in range(Y.shape[1]):
        scores = [per_class_f1(Y[:, [k]], P[:, [k]], [t])[0]["f1"] for t in THRESHOLD_GRID]
        best.append(THRESHOLD_GRID[int(np.argmax(scores))])  # ties: lowest threshold
    return best


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sources", nargs="+", default=["ledgar", "cuad"])
    parser.add_argument("--models", nargs="+", default=list(candidates()))
    args = parser.parse_args(argv)
    settings = get_settings()

    cats = trained_categories()
    train, val = load_split("train", tuple(args.sources)), load_split("val", tuple(args.sources))
    if not train or not val:
        print(
            "error: no prepared data; run prepare_ledgar.py / prepare_cuad.py first",
            file=sys.stderr,
        )
        return 2
    sources_found = sorted({r["source"] for r in train})
    no_data = [c for c in cats if not any(c in r["labels"] for r in train)]
    if no_data:
        print(f"warning: no training positives for {no_data}; these categories are left out")
        cats = [c for c in cats if c not in no_data]
    Ytr, Yva = label_matrix(train, cats), label_matrix(val, cats)
    Xtr_text, Xva_text = [r["text"] for r in train], [r["text"] for r in val]
    print(
        f"train {len(train)} rows, val {len(val)} rows, sources {sources_found}, categories {cats}"
    )

    features: dict[str, tuple[Any, Any, Any]] = {}
    results: list[dict] = []
    best: dict | None = None
    for name in args.models:
        kind, grid = candidates()[name]
        if kind not in features:
            t0 = time.time()
            vec = tfidf() if kind == "tfidf" else MiniLMEncoder(settings.embeddings.model_name)
            try:
                Xtr = vec.fit_transform(Xtr_text)
                Xva = vec.transform(Xva_text)
            except Exception as exc:
                print(
                    f"{name}: features '{kind}' unavailable ({type(exc).__name__}: {exc}); skipped"
                )
                results.append({"model": name, "status": f"skipped: {type(exc).__name__}"})
                continue
            features[kind] = (vec, Xtr, Xva)
            print(f"features {kind}: {Xtr.shape} in {time.time() - t0:.0f}s")
        vec, Xtr, Xva = features[kind]
        for params, clf in grid:
            t0 = time.time()
            model = MaskedOneVsRest(clf).fit(Xtr, Ytr)
            score = macro_f1(Yva, model.predict_proba(Xva))
            row = {
                "model": name,
                "params": params,
                "val_macro_f1": round(score, 4),
                "fit_seconds": round(time.time() - t0, 1),
                "status": "ok",
            }
            print(row)
            results.append(row)
            if best is None or score > best["score"]:
                best = {
                    "name": name,
                    "params": params,
                    "score": score,
                    "vec": vec,
                    "model": model,
                    "Xva": Xva,
                }

    if best is None:
        print("error: no model could be trained", file=sys.stderr)
        return 1
    P = best["model"].predict_proba(best["Xva"])
    thresholds = tune_thresholds(Yva, P)
    tuned = macro_f1(Yva, P, thresholds)
    pipeline = Pipeline([("features", best["vec"]), ("clf", best["model"])])

    model_path = settings.resolve_path(settings.classification.model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "pipeline": pipeline,
            "categories": cats,
            "model_name": best["name"],
            "params": best["params"],
            "sources": sources_found,
        },
        model_path,
    )
    thr = dict(zip(cats, thresholds, strict=True))
    settings.resolve_path(settings.classification.thresholds_path).write_text(
        json.dumps(thr, indent=2) + "\n"
    )

    summary = {
        "sources": sources_found,
        "categories": cats,
        "train_rows": len(train),
        "val_rows": len(val),
        "selected": {
            "model": best["name"],
            "params": best["params"],
            "val_macro_f1_at_0.5": round(best["score"], 4),
            "val_macro_f1_tuned": round(tuned, 4),
            "thresholds": thr,
        },
        "comparison": results,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "classification_models.json").write_text(json.dumps(summary, indent=2) + "\n")
    (RESULTS / "classification_models.md").write_text(to_markdown(summary))
    print(to_markdown(summary))
    return 0


def to_markdown(s: dict) -> str:
    lines = [
        "# Clause classifier comparison (validation)",
        "",
        f"Sources: {', '.join(s['sources'])}. Train rows {s['train_rows']}, validation rows "
        f"{s['val_rows']}. Macro-F1 over {len(s['categories'])} categories at threshold 0.5, "
        "masked by source coverage (D39).",
        "",
        "| Model | Params | Val macro-F1 | Fit (s) | Status |",
        "|---|---|---|---|---|",
    ]
    for r in s["comparison"]:
        lines.append(
            f"| {r['model']} | {r.get('params', '')} | {r.get('val_macro_f1', '')} | "
            f"{r.get('fit_seconds', '')} | {r['status']} |"
        )
    sel = s["selected"]
    lines += [
        "",
        f"Selected: **{sel['model']}** {sel['params']}; validation macro-F1 "
        f"{sel['val_macro_f1_at_0.5']} at 0.5, {sel['val_macro_f1_tuned']} with tuned thresholds.",
        "",
        "| Category | Threshold |",
        "|---|---|",
        *[f"| {c} | {t} |" for c, t in sel["thresholds"].items()],
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
