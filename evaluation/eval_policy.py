"""Phase 6 acceptance: policy engine against gold rule statuses (HLD 8, E5), LLM off.

``--categories gold`` (default until the Phase 4 classifier exists) gives each predicted clause the
categories of its gold clause, so the score isolates segmentation + facts + engine.
``--categories model`` uses the trained classifier (Phase 4 artifacts) for the end-to-end figure.
Without the embedding model, the semantic NEEDS_REVIEW step (8.3 step 3) is skipped.

Scored: the per-status confusion matrix over all (contract, rule) pairs, and violation precision /
recall, where a violation is NON_COMPLIANT or MISSING (targets: recall >= 0.85, precision >= 0.80).

Usage:
    python evaluation/eval_policy.py [--categories gold|model] [--no-embeddings]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_facts import with_gold_categories  # noqa: E402
from eval_segmentation import FORMATS, GOLD, RESULTS  # noqa: E402

from contractguard.embeddings.service import Embedder, try_load_embedder  # noqa: E402
from contractguard.extraction.document import extract_meta  # noqa: E402
from contractguard.extraction.facts import extract_facts  # noqa: E402
from contractguard.ingestion.router import load_document  # noqa: E402
from contractguard.models import Clause  # noqa: E402
from contractguard.policy.engine import evaluate_policy  # noqa: E402
from contractguard.policy.schema import load_policy  # noqa: E402
from contractguard.preprocessing.cleaner import clean_document  # noqa: E402
from contractguard.segmentation.segmenter import segment  # noqa: E402

STATUSES = ("NON_COMPLIANT", "MISSING", "NEEDS_REVIEW", "COMPLIANT", "NOT_APPLICABLE")
VIOLATIONS = frozenset({"NON_COMPLIANT", "MISSING"})
RECALL_TARGET, PRECISION_TARGET = 0.85, 0.80

Classify = Callable[[list[Clause]], list[Clause]]


def predict_statuses(
    gold: dict, path: Path, classify: Classify | None, embedder: Embedder | None
) -> dict[str, str]:
    doc = load_document(path)
    clauses = segment(clean_document(doc), doc)
    clauses = classify(clauses) if classify else with_gold_categories(gold["clauses"], clauses)
    meta = extract_meta(clauses, gold["our_org"])
    facts = extract_facts(clauses, meta.parties)
    policy = load_policy("default_vendor_v1")
    findings = evaluate_policy(policy, meta.contract_type, clauses, facts, embedder)
    return {f.rule_id: f.status for f in findings}


def violation_scores(pairs: list[tuple[str, str]]) -> dict[str, float | int | None]:
    tp = sum(g in VIOLATIONS and p in VIOLATIONS for g, p in pairs)
    fp = sum(g not in VIOLATIONS and p in VIOLATIONS for g, p in pairs)
    fn = sum(g in VIOLATIONS and p not in VIOLATIONS for g, p in pairs)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "status_accuracy": round(sum(g == p for g, p in pairs) / len(pairs), 4) if pairs else None,
    }  # fmt: skip


def confusion(pairs: list[tuple[str, str]]) -> dict[str, dict[str, int]]:
    return {g: {p: sum(1 for x in pairs if x == (g, p)) for p in STATUSES} for g in STATUSES}


def evaluate(
    classify: Classify | None = None, embedder: Embedder | None = None, gold_dir: Path = GOLD
) -> dict:
    rows = []
    for contract in sorted(p for p in gold_dir.iterdir() if (p / "gold.json").exists()):
        gold = json.loads((contract / "gold.json").read_text())
        row: dict = {"contract": contract.name}
        for fmt, name in FORMATS.items():
            try:
                pred = predict_statuses(gold, contract / name, classify, embedder)
                row[fmt] = {
                    "ok": True,
                    "rules": {
                        rid: {"gold": g["status"], "pred": pred.get(rid)}
                        for rid, g in gold["rules"].items()
                    },
                }
            except Exception as exc:  # report, do not stop the run
                row[fmt] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        rows.append(row)

    summary = {}
    for fmt in FORMATS:
        pairs = [
            (r["gold"], r["pred"])
            for row in rows
            if row[fmt]["ok"]
            for r in row[fmt]["rules"].values()
        ]
        summary[fmt] = {
            **violation_scores(pairs),
            "confusion": confusion(pairs),
            "failed_files": sum(not row[fmt]["ok"] for row in rows),
        }
    return {
        "categories": "model" if classify else "gold",
        "embeddings": embedder is not None,
        "targets": {"recall": RECALL_TARGET, "precision": PRECISION_TARGET},
        "summary": summary,
        "contracts": rows,
    }


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.1%}"


def to_markdown(report: dict) -> str:
    fmts = list(report["summary"])
    src = (
        "the trained classifier" if report["categories"] == "model"
        else "the gold labels (draft); no classifier"
    )  # fmt: skip
    emb = "on" if report["embeddings"] else "off (semantic NEEDS_REVIEW step skipped)"
    lines = [
        f"# Policy engine check (E5, categories from {report['categories']})",
        "",
        f"LLM off. Clause categories come from {src}. Embeddings: {emb}. Targets: violation "
        f"recall >= {RECALL_TARGET:.0%}, precision >= {PRECISION_TARGET:.0%}.",
        "",
        "| Measure | " + " | ".join(fmts) + " |",
        "|---" * (len(fmts) + 1) + "|",
    ]
    for key, label in (("recall", "**Violation recall**"), ("precision", "**Violation precision**"),
                       ("status_accuracy", "Exact status accuracy")):  # fmt: skip
        lines.append(
            f"| {label} | " + " | ".join(_pct(report["summary"][f][key]) for f in fmts) + " |"
        )
    for key in ("tp", "fp", "fn", "failed_files"):
        lines.append(
            f"| {key} | " + " | ".join(str(report["summary"][f][key]) for f in fmts) + " |"
        )

    for fmt in fmts:
        cm = report["summary"][fmt]["confusion"]
        lines += ["", f"## Confusion matrix: {fmt} (rows gold, columns predicted)", "",
                  "| gold \\ pred | " + " | ".join(STATUSES) + " |",
                  "|---" * (len(STATUSES) + 1) + "|"]  # fmt: skip
        for g in STATUSES:
            lines.append(f"| {g} | " + " | ".join(str(cm[g][p]) for p in STATUSES) + " |")

    errors = []
    for row in report["contracts"]:
        for fmt in fmts:
            v = row[fmt]
            if not v["ok"]:
                errors.append(f"| {row['contract']} | {fmt} | FAILED | {v['error']} | |")
                continue
            for rid, r in v["rules"].items():
                if r["gold"] != r["pred"]:
                    errors.append(
                        f"| {row['contract']} | {fmt} | {rid} | {r['gold']} | {r['pred']} |"
                    )
    lines += ["", "## Disagreements", ""]
    lines += (
        ["| Contract | Format | Rule | Gold | Predicted |", "|---|---|---|---|---|", *errors]
        if errors else ["None."]
    )  # fmt: skip
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--categories", choices=["gold", "model"], default="gold")
    parser.add_argument("--no-embeddings", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    args = parser.parse_args(argv)

    classify: Classify | None = None
    if args.categories == "model":
        from contractguard.classification.classifier import load_classifier

        classify = load_classifier().classify
    embedder = None if args.no_embeddings else try_load_embedder()
    report = evaluate(classify, embedder)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"policy_{args.categories}"
    (args.out_dir / f"{stem}.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.out_dir / f"{stem}.md").write_text(to_markdown(report))
    print(to_markdown(report))
    ok = all(
        (s["recall"] or 0) >= RECALL_TARGET and (s["precision"] or 0) >= PRECISION_TARGET
        and not s["failed_files"]
        for s in report["summary"].values()
    )  # fmt: skip
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
