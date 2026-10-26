"""Shared helpers for the training scripts: paths, JSONL I/O, label coverage (D39)."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

import numpy as np

from contractguard.config import REPO_ROOT, get_label_map

RAW = REPO_ROOT / "data" / "raw"
PROCESSED = REPO_ROOT / "data" / "processed"
RESULTS = REPO_ROOT / "evaluation" / "results"
SPLITS = ("train", "val", "test")
SEED = 42


def trained_categories() -> list[str]:
    """The categories a dataset label maps to (8 in V1: all but SLA and OTHER)."""
    lm = get_label_map()
    cats: dict[str, None] = {}
    for source in ("ledgar", "cuad"):
        for cat, names in lm.get(source, {}).items():
            if names:
                cats.setdefault(cat, None)
    order = [
        "CONFIDENTIALITY",
        "TERMINATION",
        "PAYMENT",
        "LIABILITY",
        "INDEMNIFICATION",
        "IP",
        "GOVERNING_LAW",
        "RENEWAL",
    ]
    return [c for c in order if c in cats] + sorted(c for c in cats if c not in order)


def negative_coverage() -> dict[str, set[str]]:
    """Per source, the categories for which an unlabelled example is a true negative."""
    lm = get_label_map()
    ledgar = {c for c, names in lm.get("ledgar", {}).items() if names}
    return {"ledgar": ledgar, "cuad": set(lm.get("cuad_negatives", []))}


def label_matrix(rows: list[dict], categories: list[str]) -> np.ndarray:
    """1 = positive, 0 = negative, -1 = unknown (the source has no labels for that category)."""
    cover = negative_coverage()
    Y = np.full((len(rows), len(categories)), -1, dtype=int)
    for i, row in enumerate(rows):
        labels = set(row["labels"])
        known = cover.get(row["source"], set())
        for k, cat in enumerate(categories):
            if cat in labels:
                Y[i, k] = 1
            elif cat in known:
                Y[i, k] = 0
    return Y


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def load_split(split: str, sources: tuple[str, ...] = ("ledgar", "cuad")) -> list[dict]:
    """Merged rows of one split from every prepared source that exists on disk."""
    rows: list[dict] = []
    for source in sources:
        path = PROCESSED / f"{source}_{split}.jsonl"
        if path.is_file():
            rows += read_jsonl(path)
    return rows
