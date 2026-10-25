"""Print every LEDGAR and CUAD label name and check config/label_map.yaml against them (HLD 6.4).

Usage:
    pip install -e ".[training]"
    python training/inspect_labels.py

Writes docs/labels_ledgar.txt and docs/labels_cuad.txt as evidence, then lists every name in
label_map.yaml that does not exist in the dataset. Exit code 1 if any mapped name is unknown.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from contractguard.config import REPO_ROOT, get_label_map

CUAD_QUESTION = re.compile(r'related to "(?P<cat>[^"]+)"')


def ledgar_labels() -> list[str]:
    from datasets import load_dataset

    ds = load_dataset("coastalcph/lex_glue", "ledgar")
    return list(ds["train"].features["label"].names)


def cuad_labels() -> list[str]:
    """CUAD categories, parsed from the QA questions of ``theatticusproject/cuad-qa``."""
    from datasets import load_dataset

    ds = load_dataset("theatticusproject/cuad-qa", split="train")
    found: dict[str, None] = {}
    for question in ds["question"]:
        m = CUAD_QUESTION.search(question)
        if m:
            found.setdefault(m.group("cat"), None)
    return list(found)


def unknown_names(mapping: dict[str, list[str]], available: list[str]) -> list[str]:
    known = set(available)
    return [name for names in mapping.values() for name in names if name not in known]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "docs")
    args = parser.parse_args(argv)

    label_map = get_label_map()
    problems = 0
    for source, loader in (("ledgar", ledgar_labels), ("cuad", cuad_labels)):
        names = loader()
        out = args.out_dir / f"labels_{source}.txt"
        out.write_text("\n".join(names) + "\n", encoding="utf-8")
        print(f"== {source}: {len(names)} labels (written to {out})")
        for name in names:
            print(f"  {name}")
        missing = unknown_names(label_map.get(source, {}), names)
        for name in missing:
            print(f"!! label_map.yaml [{source}] maps '{name}', which is not a {source} label")
        problems += len(missing)

    if problems:
        print(f"\n{problems} unknown name(s): fix config/label_map.yaml before training.")
        return 1
    print("\nAll mapped names exist. Set `verified: true` in config/label_map.yaml.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
