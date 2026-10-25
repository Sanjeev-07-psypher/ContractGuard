"""End-to-end evaluation on the gold set with the trained models (HLD 12: E3, E5, E6, E8).

For every gold contract and format the full pipeline runs with the LLM off (E5 must not depend on
it). Scored:

* E5  per-status confusion matrix and violation precision / recall (NON_COMPLIANT + MISSING);
* E3  agreement of rule statuses between the text PDF and the scanned PDF of each contract;
* E6  semantic retrieval: each rule's ``policy_text`` against the contract's BODY clauses;
      a hit is a clause inside one of the rule's gold clauses. Precision@3, Recall@3, MRR;
* E8  seconds per contract (NLP only) by format, with the per-stage split.

Needs the Phase 4 artifacts and the embedding model. The gold set is never used for training or
tuning.

Usage:
    python evaluation/run_e2e_eval.py
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_policy import STATUSES, confusion, violation_scores  # noqa: E402
from eval_segmentation import FORMATS, GOLD, RESULTS, match  # noqa: E402

from contractguard.embeddings.service import Embedder, cosine_top_k  # noqa: E402
from contractguard.models import Clause, Report  # noqa: E402
from contractguard.pipeline import Options, Resources, run  # noqa: E402
from contractguard.policy.schema import load_policy  # noqa: E402

TARGETS = {
    "recall": 0.85,
    "precision": 0.80,
    "e3_agreement": 0.90,
    "p_at_3": 0.70,
    "e8_seconds": 30,
}
K = 3


def _in_gold(number: str | None, gold_numbers: list[str]) -> bool:
    return number is not None and any(
        number == g or number.startswith(f"{g}.") for g in gold_numbers
    )


def retrieval(gold: dict, clauses: list[Clause], embedder: Embedder) -> list[dict]:
    """E6 for one contract: rank BODY clauses by similarity to each rule's policy text."""
    body = [c for c in clauses if c.kind == "BODY"]
    if not body:
        return []
    pairs = dict((p, g) for g, p in match(gold["clauses"], body))
    gold_number = {i: gold["clauses"][g]["number"] for i, g in pairs.items()}
    matrix = embedder.encode([c.text for c in body])
    policy = {r.id: r for r in load_policy("default_vendor_v1").rules}
    out = []
    for rid, g in gold["rules"].items():
        if not g.get("clauses"):
            continue
        relevant = {i for i in range(len(body)) if _in_gold(gold_number.get(i), g["clauses"])}
        if not relevant:
            continue
        ranked = [
            i
            for i, _ in cosine_top_k(
                embedder.encode([policy[rid].policy_text])[0], matrix, k=len(body)
            )
        ]
        top = ranked[:K]
        hits = [i in relevant for i in top]
        first = next((n + 1 for n, i in enumerate(ranked) if i in relevant), None)
        out.append(
            {
                "rule": rid,
                "p_at_3": sum(hits) / K,
                "r_at_3": sum(hits) / len(relevant),
                "rr": 1 / first if first else 0.0,
            }
        )
    return out


def evaluate(resources: Resources, gold_dir: Path = GOLD) -> dict:
    rows = []
    for contract in sorted(p for p in gold_dir.iterdir() if (p / "gold.json").exists()):
        gold = json.loads((contract / "gold.json").read_text())
        row: dict = {"contract": contract.name}
        for fmt, name in FORMATS.items():
            t0 = time.perf_counter()
            try:
                report: Report = run(
                    contract / name, Options(our_org_name=gold["our_org"], use_llm=False), resources
                )
            except Exception as exc:
                row[fmt] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                continue
            seconds = time.perf_counter() - t0
            pred = {f.rule_id: f.status for f in report.findings}
            row[fmt] = {
                "ok": True,
                "seconds": round(seconds, 2),
                "timings": report.timings_s,
                "pages": report.num_pages,
                "rules": {
                    rid: {"gold": g["status"], "pred": pred.get(rid)}
                    for rid, g in gold["rules"].items()
                },
                "retrieval": retrieval(gold, report.clauses, resources.embedder)
                if resources.embedder
                else [],
            }
        rows.append(row)
    return {"targets": TARGETS, "summary": summarize(rows), "contracts": rows}


def summarize(rows: list[dict]) -> dict:
    out: dict = {}
    for fmt in FORMATS:
        ok = [r[fmt] for r in rows if r[fmt]["ok"]]
        pairs = [(x["gold"], x["pred"]) for o in ok for x in o["rules"].values()]
        ret = [q for o in ok for q in o["retrieval"]]
        out[fmt] = {
            **violation_scores(pairs),
            "confusion": confusion(pairs),
            "failed_files": len(rows) - len(ok),
            "seconds_mean": round(statistics.mean(o["seconds"] for o in ok), 2) if ok else None,
            "seconds_max": round(max(o["seconds"] for o in ok), 2) if ok else None,
            "p_at_3": round(statistics.mean(q["p_at_3"] for q in ret), 4) if ret else None,
            "r_at_3": round(statistics.mean(q["r_at_3"] for q in ret), 4) if ret else None,
            "mrr": round(statistics.mean(q["rr"] for q in ret), 4) if ret else None,
            "retrieval_queries": len(ret),
        }
    agree = [
        r["text_pdf"]["rules"][rid]["pred"] == r["scanned_pdf"]["rules"][rid]["pred"]
        for r in rows
        if r["text_pdf"]["ok"] and r["scanned_pdf"]["ok"]
        for rid in r["text_pdf"]["rules"]
    ]
    out["e3_text_vs_scanned_agreement"] = round(sum(agree) / len(agree), 4) if agree else None
    return out


def _f(v: object, pct: bool = True) -> str:
    if v is None:
        return "n/a"
    return f"{v:.1%}" if pct and isinstance(v, float) else str(v)


def to_markdown(r: dict) -> str:
    s, t = r["summary"], r["targets"]
    fmts = list(FORMATS)
    lines = [
        "# End-to-end evaluation on the gold set (E3, E5, E6, E8)",
        "",
        "Full pipeline with the trained classifier, LLM off. Gold labels are still a draft "
        "(see evaluation/gold/ADJUDICATION.md).",
        "",
        "| Measure | Target | " + " | ".join(fmts) + " |",
        "|---|---|" + "---|" * len(fmts),
    ]
    rows = [
        ("E5 violation recall", f">= {t['recall']:.0%}", "recall"),
        ("E5 violation precision", f">= {t['precision']:.0%}", "precision"),
        ("E5 exact status accuracy", "", "status_accuracy"),
        ("E6 Precision@3", f">= {t['p_at_3']:.0%}", "p_at_3"),
        ("E6 Recall@3", "", "r_at_3"),
        ("E6 MRR", "", "mrr"),
        ("E8 seconds per contract (mean)", f"< {t['e8_seconds']} s", "seconds_mean"),
        ("E8 seconds per contract (max)", "", "seconds_max"),
        ("Failed files", "0", "failed_files"),
    ]
    for label, target, key in rows:
        pct = not key.startswith(("seconds", "failed"))
        lines.append(
            f"| {label} | {target} | " + " | ".join(_f(s[f][key], pct) for f in fmts) + " |"
        )
    lines += [
        "",
        f"E3 status agreement, text PDF vs scanned PDF: "
        f"**{_f(s['e3_text_vs_scanned_agreement'])}** (target >= {t['e3_agreement']:.0%}).",
    ]
    for fmt in fmts:
        cm = s[fmt]["confusion"]
        lines += [
            "",
            f"## E5 confusion matrix: {fmt} (rows gold, columns predicted)",
            "",
            "| gold \\ pred | " + " | ".join(STATUSES) + " |",
            "|---" * (len(STATUSES) + 1) + "|",
        ]
        lines += [
            f"| {g} | " + " | ".join(str(cm[g][p]) for p in STATUSES) + " |" for g in STATUSES
        ]
    errors = [
        f"| {row['contract']} | {fmt} | {rid} | {x['gold']} | {x['pred']} |"
        for row in r["contracts"]
        for fmt in fmts
        if row[fmt]["ok"]
        for rid, x in row[fmt]["rules"].items()
        if x["gold"] != x["pred"]
    ]
    failed = [
        f"| {row['contract']} | {fmt} | FAILED | {row[fmt]['error']} | |"
        for row in r["contracts"]
        for fmt in fmts
        if not row[fmt]["ok"]
    ]
    lines += ["", "## Disagreements", ""]
    lines += (
        [
            "| Contract | Format | Rule | Gold | Predicted |",
            "|---|---|---|---|---|",
            *failed,
            *errors,
        ]
        if errors or failed
        else ["None."]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    args = parser.parse_args(argv)
    resources = Resources.load(with_llm=False)
    report = evaluate(resources)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "e2e.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.out_dir / "e2e.md").write_text(to_markdown(report))
    print(to_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
