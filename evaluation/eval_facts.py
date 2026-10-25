"""Phase 5 acceptance: fact extraction accuracy against the gold set (HLD 7, E4).

The Phase 4 classifier does not exist yet, so each predicted clause takes the categories of the
gold clause it matches (same matching as eval_segmentation.py). These scores therefore measure the
extractors on correctly classified clauses; the end-to-end figure comes in Phase 10.

Scored: the 7 gold facts (exact match; a gold None must be predicted as None) and the contract
metadata (parties with aliases and roles, effective date, expiry date, governing law, type).

Usage:
    python evaluation/eval_facts.py     # writes evaluation/results/facts.{json,md}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_segmentation import FORMATS, GOLD, RESULTS, match  # noqa: E402

from contractguard.extraction.document import extract_meta  # noqa: E402
from contractguard.extraction.facts import FACT_KEYS, extract_facts  # noqa: E402
from contractguard.ingestion.router import load_document  # noqa: E402
from contractguard.models import Clause, ContractMeta  # noqa: E402
from contractguard.preprocessing.cleaner import clean_document  # noqa: E402
from contractguard.segmentation.segmenter import segment  # noqa: E402

E4_TARGET = 0.85
META_KEYS = ("parties", "effective_date", "expiry_date", "governing_law", "contract_type")


def with_gold_categories(gold_clauses: list[dict], clauses: list[Clause]) -> list[Clause]:
    out = [c.model_copy(update={"categories": []}) for c in clauses]
    for gi, pi in match(gold_clauses, clauses):
        out[pi].categories = list(gold_clauses[gi]["categories"])
    return out


def _meta_values(meta: ContractMeta) -> dict:
    return {
        "parties": [[p.name, p.alias, p.role] for p in meta.parties],
        "effective_date": meta.effective_date.isoformat() if meta.effective_date else None,
        "expiry_date": meta.expiry_date.isoformat() if meta.expiry_date else None,
        "governing_law": meta.governing_law,
        "contract_type": meta.contract_type,
    }


def _gold_meta(gold: dict) -> dict:
    m = gold["meta"]
    return {
        "parties": [[p["name"], p["alias"], p["role"]] for p in m["parties"]],
        "effective_date": m["effective_date"],
        "expiry_date": m["expiry_date"],
        "governing_law": m["governing_law"],
        "contract_type": gold["contract_type"],
    }


def score_file(gold: dict, path: Path) -> dict:
    doc = load_document(path)
    clauses = with_gold_categories(gold["clauses"], segment(clean_document(doc), doc))
    meta = extract_meta(clauses, gold["our_org"])
    facts = extract_facts(clauses, meta.parties)
    predicted_meta, expected_meta = _meta_values(meta), _gold_meta(gold)
    return {
        "ok": True,
        "facts": {
            k: {"gold": gold["facts"][k], "pred": facts[k].value,
                "ok": facts[k].value == gold["facts"][k]}
            for k in FACT_KEYS
        },
        "meta": {
            k: {"gold": expected_meta[k], "pred": predicted_meta[k],
                "ok": predicted_meta[k] == expected_meta[k]}
            for k in META_KEYS
        },
    }  # fmt: skip


def _acc(hits: list[bool]) -> float | None:
    return round(sum(hits) / len(hits), 4) if hits else None


def evaluate(gold_dir: Path = GOLD) -> dict:
    rows = []
    for contract in sorted(p for p in gold_dir.iterdir() if (p / "gold.json").exists()):
        gold = json.loads((contract / "gold.json").read_text())
        row: dict = {"contract": contract.name}
        for fmt, name in FORMATS.items():
            try:
                row[fmt] = score_file(gold, contract / name)
            except Exception as exc:  # report, do not stop the run
                row[fmt] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        rows.append(row)

    summary: dict = {}
    for fmt in FORMATS:
        ok = [r[fmt] for r in rows if r[fmt]["ok"]]
        facts = [f for x in ok for f in x["facts"].values()]
        summary[fmt] = {
            "fact_accuracy": _acc([f["ok"] for f in facts]),
            "fact_accuracy_non_null_gold": _acc([f["ok"] for f in facts if f["gold"] is not None]),
            "per_fact": {k: _acc([x["facts"][k]["ok"] for x in ok]) for k in FACT_KEYS},
            "per_meta": {k: _acc([x["meta"][k]["ok"] for x in ok]) for k in META_KEYS},
            "failed_files": len(rows) - len(ok),
        }
    return {"e4_target": E4_TARGET, "summary": summary, "contracts": rows}


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def to_markdown(report: dict) -> str:
    fmts = list(report["summary"])
    lines = [
        "# Fact extraction check (Phase 5)",
        "",
        f"E4 target: fact exact-match accuracy >= {report['e4_target']:.0%}. Clause categories "
        "come from the gold labels (no classifier yet), and the gold labels are still a DRAFT.",
        "",
        "| Measure | " + " | ".join(fmts) + " |",
        "|---" * (len(fmts) + 1) + "|",
    ]

    def row(label: str, getter) -> None:
        lines.append(
            f"| {label} | " + " | ".join(_pct(getter(report["summary"][f])) for f in fmts) + " |"
        )

    row("**All facts (E4)**", lambda s: s["fact_accuracy"])
    row("Facts with a non-null gold value", lambda s: s["fact_accuracy_non_null_gold"])
    for k in FACT_KEYS:
        row(f"`{k}`", lambda s, k=k: s["per_fact"][k])
    for k in META_KEYS:
        row(f"meta `{k}`", lambda s, k=k: s["per_meta"][k])
    lines.append(
        "| Failed files | "
        + " | ".join(str(report["summary"][f]["failed_files"]) for f in fmts)
        + " |"
    )

    errors = []
    for r in report["contracts"]:
        for fmt in fmts:
            v = r[fmt]
            if not v["ok"]:
                errors.append(f"| {r['contract']} | {fmt} | FAILED | {v['error']} | |")
                continue
            for group in ("facts", "meta"):
                for k, x in v[group].items():
                    if not x["ok"]:
                        errors.append(
                            f"| {r['contract']} | {fmt} | {k} | {x['gold']} | {x['pred']} |"
                        )
    lines += ["", "## Errors", ""]
    if errors:
        lines += [
            "| Contract | Format | Field | Gold | Predicted |",
            "|---|---|---|---|---|",
            *errors,
        ]
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    args = parser.parse_args(argv)
    report = evaluate()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "facts.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.out_dir / "facts.md").write_text(to_markdown(report))
    print(to_markdown(report))
    ok = all(
        s["fact_accuracy"] is not None and s["fact_accuracy"] >= E4_TARGET and not s["failed_files"]
        for s in report["summary"].values()
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
