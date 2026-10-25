"""E7: build the LLM explanation rating sheet and the automatic checks (HLD 12.1).

Runs the pipeline with the configured LLM on the gold set (text PDFs), collects up to 30 flagged
findings (NON_COMPLIANT, MISSING, NEEDS_REVIEW), and writes ``evaluation/llm_rating_sheet.csv``
with empty columns for two raters (1-5 on faithfulness, relevance, clarity, actionability) plus a
hallucinated-values count. Automatic part: share of explanations that came from the LLM (i.e. passed
the grounding and number checks) and the explainer's failure counters.

Demo only with synthetic or public contracts: free-tier Gemini data may be used by Google.

Usage:
    # set LLM_PROVIDER, LLM_MODEL and GEMINI_API_KEY in .env first
    python evaluation/make_rating_sheet.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_segmentation import GOLD, RESULTS  # noqa: E402

from contractguard.config import REPO_ROOT  # noqa: E402
from contractguard.pipeline import Options, Resources, run  # noqa: E402

N_FINDINGS = 30
SHEET = REPO_ROOT / "evaluation" / "llm_rating_sheet.csv"
RATER_COLUMNS = [
    f"rater{r}_{m}"
    for r in (1, 2)
    for m in ("faithfulness", "relevance", "clarity", "actionability", "hallucinated_values")
]


def main() -> int:
    resources = Resources.load(cache_path=REPO_ROOT / "data" / "contractguard.db")
    if resources.provider is None:
        print(
            "error: no LLM configured (set LLM_PROVIDER, LLM_MODEL and GEMINI_API_KEY)",
            file=sys.stderr,
        )
        return 2
    rows: list[dict] = []
    sources = {"llm": 0, "template": 0}
    for contract in sorted(p for p in GOLD.iterdir() if (p / "gold.json").exists()):
        gold = json.loads((contract / "gold.json").read_text())
        report = run(
            contract / "contract_text.pdf", Options(our_org_name=gold["our_org"]), resources
        )
        by_id = {c.clause_id: c for c in report.clauses}
        for f in report.findings:
            if f.explanation is None:
                continue
            sources[f.explanation.source] += 1
            if len(rows) >= N_FINDINGS:
                continue
            e = f.explanation
            rows.append(
                {
                    "id": f"{contract.name}-{f.rule_id}",
                    "status": f.status,
                    "severity": f.severity,
                    "rule": f.rule_name,
                    "expected": f.expected,
                    "found": f.found,
                    "location": f.location,
                    "clause_text": "\n\n".join(by_id[i].text for i in f.clause_ids if i in by_id),
                    "source": e.source,
                    "model": e.model,
                    "summary": e.summary,
                    "explanation": e.explanation,
                    "why_it_matters": e.why_it_matters,
                    "suggested_review_action": e.suggested_review_action,
                    "quoted_evidence": e.quoted_evidence,
                    **dict.fromkeys(RATER_COLUMNS, ""),
                }
            )
    with SHEET.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["id"])
        writer.writeheader()
        writer.writerows(rows)
    total = sum(sources.values())
    summary = {
        "provider": resources.provider.name,
        "model": resources.provider.model,
        "flagged_findings": total,
        "llm_explanations": sources["llm"],
        "template_fallbacks": sources["template"],
        "grounding_pass_rate": round(sources["llm"] / total, 4) if total else None,
        "rows_in_sheet": len(rows),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "llm_auto_checks.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(f"Rating sheet: {SHEET} ({len(rows)} rows). Two raters fill the rater columns.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
