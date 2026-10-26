"""E1: evaluate the saved classifier on the test split (HLD 6.4, 12.1).

Reports per-class precision / recall / F1 with the tuned thresholds, macro and micro F1 (masked by
source coverage, D39), the same per source (LEDGAR, CUAD), and a confusion matrix over test rows
with exactly one gold category (rows: gold; columns: highest-scoring predicted category above its
threshold, or NONE). Target: macro-F1 >= 0.75.

Outputs: evaluation/results/classification_test.{json,md}, classification_confusion.png

Usage:
    python training/evaluate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RESULTS, label_matrix, load_split  # noqa: E402
from train_classifier import macro_f1, micro_f1, per_class_f1  # noqa: E402

from contractguard.classification.classifier import load_classifier  # noqa: E402

E1_TARGET = 0.75


def confusion(rows: list[dict], P: np.ndarray, cats: list[str], thr: list[float]) -> dict:
    labels = [*cats, "NONE"]
    cm = {g: dict.fromkeys(labels, 0) for g in cats}
    for row, p in zip(rows, P, strict=True):
        gold = [c for c in row["labels"] if c in cats]
        if len(gold) != 1:
            continue
        above = [k for k in range(len(cats)) if p[k] >= thr[k]]
        pred = cats[max(above, key=lambda k: p[k])] if above else "NONE"
        cm[gold[0]][pred] += 1
    return cm


def plot_confusion(cm: dict, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    gold = list(cm)
    pred = list(next(iter(cm.values())))
    M = np.array([[cm[g][p] for p in pred] for g in gold])
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.imshow(M, cmap="Blues")
    ax.set_xticks(range(len(pred)), pred, rotation=45, ha="right")
    ax.set_yticks(range(len(gold)), gold)
    for i in range(len(gold)):
        for j in range(len(pred)):
            ax.text(
                j,
                i,
                str(M[i, j]),
                ha="center",
                va="center",
                color="white" if M[i, j] > M.max() / 2 else "black",
                fontsize=8,
            )
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Gold")
    ax.set_title("Clause classification, test rows with one gold category")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def scores(rows: list[dict], P: np.ndarray, cats: list[str], thr: list[float]) -> dict:
    Y = label_matrix(rows, cats)
    per = per_class_f1(Y, P, thr)
    return {
        "rows": len(rows),
        "macro_f1": round(macro_f1(Y, P, thr), 4),
        "micro_f1": round(micro_f1(Y, P, thr), 4),
        "per_class": {
            c: {k: round(v, 4) if isinstance(v, float) else v for k, v in s.items()}
            for c, s in zip(cats, per, strict=True)
        },
    }


def main() -> int:
    clf = load_classifier()
    cats = clf.categories
    thr = [clf.thresholds[c] for c in cats]
    test = load_split("test")
    P = clf.predict_proba([r["text"] for r in test])
    report = {
        "model": clf.model_name,
        "target_macro_f1": E1_TARGET,
        "all": scores(test, P, cats, thr),
    }
    for source in sorted({r["source"] for r in test}):
        idx = [i for i, r in enumerate(test) if r["source"] == source]
        report[source] = scores([test[i] for i in idx], P[idx], cats, thr)
    report["confusion"] = confusion(test, P, cats, thr)

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "classification_test.json").write_text(json.dumps(report, indent=2) + "\n")
    (RESULTS / "classification_test.md").write_text(to_markdown(report))
    plot_confusion(report["confusion"], RESULTS / "classification_confusion.png")
    print(to_markdown(report))
    return 0 if report["all"]["macro_f1"] >= E1_TARGET else 1


def to_markdown(r: dict) -> str:
    groups = [g for g in r if isinstance(r[g], dict) and "macro_f1" in r[g]]
    lines = [
        f"# Clause classification on the test split (E1, model {r['model']})",
        "",
        f"Target: macro-F1 >= {r['target_macro_f1']}. Tuned per-class thresholds. "
        "Scores are masked by source coverage (D39).",
        "",
        "| Split | Rows | Macro-F1 | Micro-F1 |",
        "|---|---|---|---|",
        *[f"| {g} | {r[g]['rows']} | {r[g]['macro_f1']} | {r[g]['micro_f1']} |" for g in groups],
        "",
        "| Category | Precision | Recall | F1 | Support |",
        "|---|---|---|---|---|",
    ]
    for c, s in r["all"]["per_class"].items():
        lines.append(f"| {c} | {s['precision']} | {s['recall']} | {s['f1']} | {s['support']} |")
    cm = r["confusion"]
    pred = list(next(iter(cm.values())))
    lines += [
        "",
        "## Confusion matrix (rows gold, columns predicted)",
        "",
        "| gold \\ pred | " + " | ".join(pred) + " |",
        "|---" * (len(pred) + 1) + "|",
    ]
    lines += [f"| {g} | " + " | ".join(str(cm[g][p]) for p in pred) + " |" for g in cm]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
