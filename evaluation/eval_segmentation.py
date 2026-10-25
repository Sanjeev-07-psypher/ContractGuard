"""Phase 3 acceptance: clause boundary precision, recall and F1 against the gold set (HLD 6.3).

Each gold clause records its first eight words. A predicted clause matches a gold clause when its
opening text contains those words with a rapidfuzz partial ratio of at least 85 (so OCR slips
and a leftover running header do not break a match). Matching is one to one and in reading
order. Matched pairs are also scored for number, kind and heading.

Usage:
    python evaluation/eval_segmentation.py     # writes evaluation/results/segmentation.{json,md}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from rapidfuzz import fuzz

from contractguard.config import REPO_ROOT
from contractguard.ingestion.router import load_document
from contractguard.models import Clause
from contractguard.preprocessing.cleaner import clean_document
from contractguard.segmentation.segmenter import segment

GOLD = REPO_ROOT / "evaluation" / "gold"
RESULTS = REPO_ROOT / "evaluation" / "results"
FORMATS = {"docx": "contract.docx", "text_pdf": "contract_text.pdf",
           "scanned_pdf": "contract_scanned.pdf"}  # fmt: skip
F1_TARGET = 0.85
MATCH_SCORE = 85
LOOKAHEAD = 3  # predicted clauses skipped at most when searching for the next gold clause
_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", text).strip().lower()


def _opening(clause: Clause, gold_words: str) -> str:
    return _norm(clause.text)[: int(len(gold_words) * 1.5) + 20]


def match(gold: list[dict], pred: list[Clause]) -> list[tuple[int, int]]:
    """In-order one-to-one matches as (gold index, predicted index)."""
    pairs: list[tuple[int, int]] = []
    j = 0
    for i, g in enumerate(gold):
        words = _norm(g["first_words"])
        for k in range(j, min(j + LOOKAHEAD + 1, len(pred))):
            if fuzz.partial_ratio(words, _opening(pred[k], words)) >= MATCH_SCORE:
                pairs.append((i, k))
                j = k + 1
                break
    return pairs


def _same_heading(a: str | None, b: str | None) -> bool:
    return _norm(a or "") == _norm(b or "")


def score(gold: list[dict], pred: list[Clause]) -> dict:
    pairs = match(gold, pred)
    n = len(pairs)
    precision = n / len(pred) if pred else 0.0
    recall = n / len(gold) if gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if n else 0.0
    matched = set(i for i, _ in pairs)
    return {
        "gold": len(gold),
        "predicted": len(pred),
        "matched": n,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "number_ok": sum(gold[i]["number"] == pred[k].number for i, k in pairs),
        "kind_ok": sum(gold[i]["kind"] == pred[k].kind for i, k in pairs),
        "heading_ok": sum(_same_heading(gold[i]["heading"], pred[k].heading) for i, k in pairs),
        "missed": [gold[i]["first_words"] for i in range(len(gold)) if i not in matched],
    }


def evaluate(gold_dir: Path = GOLD) -> dict:
    rows = []
    for contract in sorted(p for p in gold_dir.iterdir() if (p / "gold.json").exists()):
        gold = json.loads((contract / "gold.json").read_text())["clauses"]
        row: dict = {"contract": contract.name}
        for fmt, name in FORMATS.items():
            try:
                doc = load_document(contract / name)
                row[fmt] = {"ok": True, **score(gold, segment(clean_document(doc), doc))}
            except Exception as exc:  # report, do not stop the run
                row[fmt] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        rows.append(row)

    summary = {}
    for fmt in FORMATS:
        ok = [r[fmt] for r in rows if r[fmt]["ok"]]
        g, p, m = (sum(x[k] for x in ok) for k in ("gold", "predicted", "matched"))
        prec, rec = (m / p if p else 0.0), (m / g if g else 0.0)
        summary[fmt] = {
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(2 * prec * rec / (prec + rec), 4) if m else 0.0,
            "number_acc": round(sum(x["number_ok"] for x in ok) / m, 4) if m else None,
            "kind_acc": round(sum(x["kind_ok"] for x in ok) / m, 4) if m else None,
            "heading_acc": round(sum(x["heading_ok"] for x in ok) / m, 4) if m else None,
            "failed_files": len(rows) - len(ok),
        }
    return {"f1_target": F1_TARGET, "summary": summary, "contracts": rows}


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def to_markdown(report: dict) -> str:
    lines = [
        "# Segmentation check (Phase 3)",
        "",
        f"Boundary F1 target: >= {report['f1_target']:.2f} (micro-averaged over clauses). "
        "Gold labels are a DRAFT until two human labellers sign off.",
        "",
        "| Format | Precision | Recall | F1 | Number acc. | Kind acc. | Heading acc. | Failed |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for fmt, s in report["summary"].items():
        lines.append(
            f"| {fmt} | {_pct(s['precision'])} | {_pct(s['recall'])} | {s['f1']:.3f} | "
            f"{_pct(s['number_acc'])} | {_pct(s['kind_acc'])} | {_pct(s['heading_acc'])} | "
            f"{s['failed_files']} |"
        )
    lines += [
        "",
        "| Contract | Format | Gold | Predicted | Matched | F1 | Missed |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in report["contracts"]:
        for fmt in FORMATS:
            v = r[fmt]
            if not v["ok"]:
                lines.append(f"| {r['contract']} | {fmt} | FAILED: {v['error']} | | | | |")
                continue
            missed = "; ".join(v["missed"]) or "-"
            lines.append(
                f"| {r['contract']} | {fmt} | {v['gold']} | {v['predicted']} | {v['matched']} | "
                f"{v['f1']:.3f} | {missed} |"
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    args = parser.parse_args(argv)
    report = evaluate()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "segmentation.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.out_dir / "segmentation.md").write_text(to_markdown(report))
    print(to_markdown(report))
    ok = all(s["f1"] >= F1_TARGET and not s["failed_files"] for s in report["summary"].values())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
