"""LEDGAR (LexGLUE) -> provision examples mapped to ContractGuard categories (HLD 6.4).

Provision text -> mapped category (single label, as a one-element list); unmapped labels -> OTHER
(empty list). In the train split OTHER is downsampled to at most 3x the largest positive class,
seed 42; validation and test keep their natural distribution (D40). LexGLUE's official
train / validation / test splits are kept.

Output: data/processed/ledgar_{train,val,test}.jsonl with text, labels, source, group_id.

Usage:
    python training/prepare_ledgar.py
"""

from __future__ import annotations

import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PROCESSED, SEED, write_jsonl  # noqa: E402

from contractguard.config import get_label_map  # noqa: E402

OTHER_RATIO = 3
SPLIT_NAMES = {"train": "train", "validation": "val", "test": "test"}


def map_rows(texts: list[str], labels: list[int], names: list[str], split: str) -> list[dict]:
    to_cat = {n: c for c, ns in get_label_map()["ledgar"].items() for n in ns or []}
    rows = []
    for i, (text, label) in enumerate(zip(texts, labels, strict=True)):
        cat = to_cat.get(names[label])
        rows.append(
            {
                "text": " ".join(text.split()),
                "labels": [cat] if cat else [],
                "source": "ledgar",
                "group_id": f"ledgar-{split}-{i}",
            }
        )
    return rows


def downsample_other(rows: list[dict], rng: random.Random) -> list[dict]:
    counts = Counter(r["labels"][0] for r in rows if r["labels"])
    cap = OTHER_RATIO * max(counts.values()) if counts else 0
    other = [i for i, r in enumerate(rows) if not r["labels"]]
    keep = set(rng.sample(other, min(cap, len(other))))
    return [r for i, r in enumerate(rows) if r["labels"] or i in keep]


def main() -> int:
    from datasets import load_dataset

    ds = load_dataset("coastalcph/lex_glue", "ledgar")
    names = ds["train"].features["label"].names
    rng = random.Random(SEED)
    for hf_split, split in SPLIT_NAMES.items():
        part = ds[hf_split]
        rows = map_rows(part["text"], part["label"], names, split)
        if split == "train":
            rows = downsample_other(rows, rng)
        n = write_jsonl(PROCESSED / f"ledgar_{split}.jsonl", rows)
        counts = Counter(r["labels"][0] if r["labels"] else "OTHER" for r in rows)
        print(f"ledgar {split}: {n} examples {dict(sorted(counts.items()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
