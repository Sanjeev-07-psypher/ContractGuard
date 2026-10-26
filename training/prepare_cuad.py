"""CUAD v1 -> paragraph-level multi-label examples (HLD 6.4 data preparation).

For each CUAD annotation of a mapped category, the containing paragraph (split on blank lines) is
a positive example. Paragraphs of the same contract with no mapped annotation are negatives,
sampled up to 5 per contract. Split by contract with GroupShuffleSplit 80/10/10, seed 42.

Input: data/raw/cuad/CUADv1.json, from github.com/TheAtticusProject/cuad (data.zip).
Output: data/processed/cuad_{train,val,test}.jsonl with text, labels, source, group_id.

Usage:
    python training/prepare_cuad.py [--cuad-json PATH]
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from bisect import bisect_right
from pathlib import Path

from sklearn.model_selection import GroupShuffleSplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PROCESSED, RAW, SEED, write_jsonl  # noqa: E402

from contractguard.config import get_label_map  # noqa: E402

PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
MIN_CHARS = 40
NEGATIVES_PER_CONTRACT = 5


def paragraphs(context: str) -> list[tuple[int, int]]:
    """(start, end) offsets of the blank-line separated paragraphs of ``context``."""
    spans, start = [], 0
    for m in PARAGRAPH_BREAK.finditer(context):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(context)))
    return spans


def normalize(text: str) -> str:
    return " ".join(text.split())


def contract_examples(doc: dict, cuad_to_cat: dict[str, str], rng: random.Random) -> list[dict]:
    para = doc["paragraphs"][0]
    context = para["context"]
    spans = paragraphs(context)
    starts = [s for s, _ in spans]
    labels: dict[int, set[str]] = {}
    for qa in para["qas"]:
        cat = cuad_to_cat.get(qa["id"].split("__")[-1])
        if cat is None:
            continue
        for ans in qa["answers"]:
            idx = bisect_right(starts, ans["answer_start"]) - 1
            if idx >= 0:
                labels.setdefault(idx, set()).add(cat)

    group = doc["title"]
    out = []
    for idx, cats in sorted(labels.items()):
        text = normalize(context[spans[idx][0] : spans[idx][1]])
        if len(text) >= MIN_CHARS:
            out.append({"text": text, "labels": sorted(cats), "source": "cuad", "group_id": group})
    unlabelled = [
        i
        for i in range(len(spans))
        if i not in labels and len(normalize(context[spans[i][0] : spans[i][1]])) >= MIN_CHARS
    ]
    for idx in sorted(rng.sample(unlabelled, min(NEGATIVES_PER_CONTRACT, len(unlabelled)))):
        text = normalize(context[spans[idx][0] : spans[idx][1]])
        out.append({"text": text, "labels": [], "source": "cuad", "group_id": group})
    return out


def split_groups(groups: list[str]) -> dict[str, set[str]]:
    """80/10/10 by contract: GroupShuffleSplit twice (80/20, then the 20 halved), seed 42."""
    unique = sorted(set(groups))
    first = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED)
    train_i, rest_i = next(first.split(unique, groups=unique))
    rest = [unique[i] for i in rest_i]
    second = GroupShuffleSplit(n_splits=1, test_size=0.5, random_state=SEED)
    val_i, test_i = next(second.split(rest, groups=rest))
    return {
        "train": {unique[i] for i in train_i},
        "val": {rest[i] for i in val_i},
        "test": {rest[i] for i in test_i},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cuad-json", type=Path, default=RAW / "cuad" / "CUADv1.json")
    args = parser.parse_args(argv)
    if not args.cuad_json.is_file():
        print(
            f"error: {args.cuad_json} not found. Download data.zip from "
            "github.com/TheAtticusProject/cuad and unzip it into data/raw/cuad/.",
            file=sys.stderr,
        )
        return 2

    cuad_to_cat = {
        name: cat for cat, names in get_label_map()["cuad"].items() for name in names or []
    }
    data = json.loads(args.cuad_json.read_text(encoding="utf-8"))["data"]
    rng = random.Random(SEED)
    rows = [row for doc in data for row in contract_examples(doc, cuad_to_cat, rng)]
    split_of = split_groups([r["group_id"] for r in rows])
    for split, members in split_of.items():
        part = [r for r in rows if r["group_id"] in members]
        n = write_jsonl(PROCESSED / f"cuad_{split}.jsonl", part)
        pos = sum(bool(r["labels"]) for r in part)
        print(f"cuad {split}: {n} examples ({pos} positive) from {len(members)} contracts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
