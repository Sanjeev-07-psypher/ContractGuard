"""Agreement between the draft gold labels and a second labelling (GUIDELINES.md §5).

The second labelling lives in ``evaluation/gold/<labeller>/labels.yaml``. Reported per contract
and overall: boundary agreement (same clause numbers), category agreement (Cohen's kappa per
category over clauses both labellers have), fact, metadata and rule-status agreement (exact match),
and every disagreement, ready for ADJUDICATION.md.

Usage:
    python evaluation/label_agreement.py --labeller labeller_ai
    # writes evaluation/results/agreement_<labeller>.{json,md}
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml
from sklearn.metrics import cohen_kappa_score

ROOT = Path(__file__).resolve().parent
GOLD = ROOT / "gold"
RESULTS = ROOT / "results"
CATEGORIES = [
    "CONFIDENTIALITY", "TERMINATION", "PAYMENT", "LIABILITY", "INDEMNIFICATION",
    "IP", "GOVERNING_LAW", "RENEWAL", "SLA", "OTHER",
]  # fmt: skip
META_KEYS = ("effective_date", "expiry_date", "governing_law")


def _key(number: str | None, kind: str, seen: dict[str, int]) -> str:
    """Clause identity: its number, or kind + position for PREAMBLE/SIGNATURE/EXHIBIT."""
    if kind in ("BODY", "DEFINITIONS") and number:
        return str(number)
    seen[kind] = seen.get(kind, 0) + 1
    return f"{kind}#{seen[kind]}"


def _gold_clauses(gold: dict[str, Any]) -> dict[str, tuple[str, set[str]]]:
    seen: dict[str, int] = {}
    return {
        _key(c["number"], c["kind"], seen): (c["kind"], set(c.get("categories") or []))
        for c in gold["clauses"]
    }


def _second_clauses(rows: list[list[Any]]) -> dict[str, tuple[str, set[str]]]:
    seen: dict[str, int] = {}
    return {_key(str(n), kind, seen): (kind, set(cats)) for n, kind, cats in rows}


def _kappa(a: list[int], b: list[int]) -> float | None:
    """Cohen's kappa; None when both labellers use one value only (kappa undefined)."""
    if len(set(a) | set(b)) < 2:
        return None
    return round(float(cohen_kappa_score(a, b)), 3)


def compare(cid: str, gold: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    g, s = _gold_clauses(gold), _second_clauses(second["clauses"])
    both = [k for k in g if k in s]
    diffs: list[dict[str, Any]] = []
    for k in sorted(set(g) ^ set(s)):
        diffs.append({"item": f"boundary {k}", "draft": k in g, "second": k in s})
    for k in both:
        if g[k][0] != s[k][0]:
            diffs.append({"item": f"kind {k}", "draft": g[k][0], "second": s[k][0]})
        if g[k][1] != s[k][1]:
            diffs.append(
                {"item": f"categories {k}", "draft": sorted(g[k][1]), "second": sorted(s[k][1])}
            )
    vectors = {
        cat: ([int(cat in g[k][1]) for k in both], [int(cat in s[k][1]) for k in both])
        for cat in CATEGORIES
    }
    facts_ok = 0
    for f, gv in gold["facts"].items():
        sv = second["facts"].get(f)
        facts_ok += gv == sv
        if gv != sv:
            diffs.append({"item": f"fact {f}", "draft": gv, "second": sv})
    meta_ok = 0
    gold_meta = dict(gold["meta"], contract_type=gold["contract_type"])
    second_meta = dict(second["meta"], contract_type=second["contract_type"])
    for m in (*META_KEYS, "contract_type"):
        meta_ok += gold_meta.get(m) == second_meta.get(m)
        if gold_meta.get(m) != second_meta.get(m):
            diffs.append(
                {"item": f"meta {m}", "draft": gold_meta.get(m), "second": second_meta.get(m)}
            )
    rules_ok = 0
    for rid, gr in gold["rules"].items():
        status, clauses = second["rules"][rid]
        rules_ok += gr["status"] == status
        if gr["status"] != status:
            diffs.append({"item": f"rule {rid}", "draft": gr["status"], "second": status})
        elif sorted(map(str, gr["clauses"] or [])) != sorted(map(str, clauses)):
            diffs.append(
                {"item": f"rule {rid} evidence", "draft": gr["clauses"], "second": clauses}
            )
    return {
        "contract": cid,
        "boundaries": {"draft": len(g), "second": len(s), "matched": len(both)},
        "category_vectors": vectors,
        "categories_exact": sum(g[k][1] == s[k][1] for k in both),
        "facts": {"ok": facts_ok, "n": len(gold["facts"])},
        "meta": {"ok": meta_ok, "n": len(META_KEYS) + 1},
        "rules": {"ok": rules_ok, "n": len(gold["rules"])},
        "disagreements": diffs,
    }


def run(labeller: str) -> dict[str, Any]:
    second_all = yaml.safe_load((GOLD / labeller / "labels.yaml").read_text())
    rows = [
        compare(cid, json.loads((GOLD / cid / "gold.json").read_text()), second)
        for cid, second in sorted(second_all.items())
    ]
    pooled = {c: ([], []) for c in CATEGORIES}
    for r in rows:
        for c, (a, b) in r.pop("category_vectors").items():
            pooled[c][0].extend(a)
            pooled[c][1].extend(b)
        r["boundaries"]["f1"] = round(
            2 * r["boundaries"]["matched"] / (r["boundaries"]["draft"] + r["boundaries"]["second"]),
            3,
        )

    def total(key: str) -> dict[str, int]:
        return {k: sum(r[key][k] for r in rows) for k in ("ok", "n")}

    matched = sum(r["boundaries"]["matched"] for r in rows)
    return {
        "labeller": labeller,
        "boundary_f1": round(
            2 * matched / sum(r["boundaries"]["draft"] + r["boundaries"]["second"] for r in rows), 3
        ),
        "category_kappa": {c: _kappa(a, b) for c, (a, b) in pooled.items()},
        "categories_exact": {"ok": sum(r["categories_exact"] for r in rows), "n": matched},
        "facts": total("facts"),
        "meta": total("meta"),
        "rules": total("rules"),
        "per_contract": rows,
    }


def to_markdown(res: dict[str, Any]) -> str:
    def pct(d: dict[str, int]) -> str:
        return f"{d['ok']}/{d['n']} ({100 * d['ok'] / d['n']:.1f}%)"

    lines = [
        f"# Label agreement: draft vs {res['labeller']}",
        "",
        "| Measure | Agreement |",
        "|---|---|",
        f"| Clause boundaries (F1 on clause identities) | {res['boundary_f1']} |",
        f"| Clause categories, exact set match | {pct(res['categories_exact'])} |",
        f"| Facts (exact) | {pct(res['facts'])} |",
        f"| Metadata: dates, governing law, type (exact) | {pct(res['meta'])} |",
        f"| Rule statuses (exact) | {pct(res['rules'])} |",
        "",
        "Cohen's kappa per category, pooled over matched clauses "
        "(— = only one value used, undefined):",
        "",
        "| Category | Kappa |",
        "|---|---|",
    ]
    lines += [f"| {c} | {'—' if k is None else k} |" for c, k in res["category_kappa"].items()]
    lines += [
        "",
        "## Disagreements",
        "",
        "| Contract | Item | Draft | Second |",
        "|---|---|---|---|",
    ]
    for r in res["per_contract"]:
        for d in r["disagreements"]:
            lines.append(f"| {r['contract']} | {d['item']} | {d['draft']} | {d['second']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--labeller", default="labeller_ai")
    args = parser.parse_args()
    res = run(args.labeller)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"agreement_{args.labeller}.json").write_text(json.dumps(res, indent=2))
    md = to_markdown(res)
    (RESULTS / f"agreement_{args.labeller}.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
