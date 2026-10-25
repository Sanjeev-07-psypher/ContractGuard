"""Phase 2 acceptance: every gold file loads, and OCR character error rate (HLD 6.1, E3).

For each gold contract, loads the DOCX, the text PDF and the scanned PDF, cleans them, and
compares the scanned text with the text-PDF text (whitespace-normalized Levenshtein CER).

Usage:
    python evaluation/eval_ingestion.py            # writes evaluation/results/ingestion.{json,md}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from rapidfuzz.distance import Levenshtein

from contractguard.config import REPO_ROOT
from contractguard.ingestion.router import load_document
from contractguard.preprocessing.cleaner import clean_document

GOLD = REPO_ROOT / "evaluation" / "gold"
RESULTS = REPO_ROOT / "evaluation" / "results"
FORMATS = {"docx": "contract.docx", "text_pdf": "contract_text.pdf",
           "scanned_pdf": "contract_scanned.pdf"}  # fmt: skip
CER_TARGET = 0.05
_WS = re.compile(r"\s+")


def cer(reference: str, hypothesis: str) -> float:
    ref, hyp = _WS.sub(" ", reference).strip(), _WS.sub(" ", hypothesis).strip()
    return Levenshtein.distance(ref, hyp) / max(len(ref), 1)


def evaluate(gold_dir: Path = GOLD) -> dict:
    rows = []
    for contract in sorted(p for p in gold_dir.iterdir() if (p / "contract.yaml").exists()):
        row: dict = {"contract": contract.name}
        texts = {}
        for fmt, name in FORMATS.items():
            start = time.perf_counter()
            try:
                doc = load_document(contract / name)
                cleaned = clean_document(doc)
                texts[fmt] = cleaned.text
                row[fmt] = {
                    "ok": True,
                    "blocks": len(doc.blocks),
                    "ocr_pages": doc.ocr_pages,
                    "warnings": doc.warnings,
                    "seconds": round(time.perf_counter() - start, 2),
                }
            except Exception as exc:  # report, do not stop the run
                row[fmt] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        if "text_pdf" in texts and "scanned_pdf" in texts:
            row["ocr_cer"] = round(cer(texts["text_pdf"], texts["scanned_pdf"]), 4)
        rows.append(row)
    loaded = sum(r[f]["ok"] for r in rows for f in FORMATS)
    cers = [r["ocr_cer"] for r in rows if "ocr_cer" in r]
    return {
        "files_loaded": loaded,
        "files_total": len(rows) * len(FORMATS),
        "ocr_cer_mean": round(sum(cers) / len(cers), 4) if cers else None,
        "ocr_cer_max": max(cers) if cers else None,
        "ocr_cer_target": CER_TARGET,
        "contracts": rows,
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2%}"


def to_markdown(report: dict) -> str:
    lines = [
        "# Ingestion check (Phase 2)",
        "",
        f"Files loaded: **{report['files_loaded']} / {report['files_total']}**. "
        f"OCR CER mean **{_pct(report['ocr_cer_mean'])}**, max {_pct(report['ocr_cer_max'])} "
        f"(target < {report['ocr_cer_target']:.0%}).",
        "",
        "| Contract | DOCX blocks | Text PDF blocks | Scanned OCR pages | OCR CER | Scan seconds |",
        "|---|---|---|---|---|---|",
    ]

    def cell(row: dict, fmt: str, key: str) -> str:
        v = row[fmt]
        return str(v[key]) if v["ok"] else f"FAILED: {v['error']}"

    for r in report["contracts"]:
        lines.append(
            f"| {r['contract']} | {cell(r, 'docx', 'blocks')} | {cell(r, 'text_pdf', 'blocks')} | "
            f"{len(r['scanned_pdf'].get('ocr_pages', []))} | {_pct(r.get('ocr_cer'))} | "
            f"{cell(r, 'scanned_pdf', 'seconds')} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    args = parser.parse_args(argv)
    report = evaluate()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "ingestion.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.out_dir / "ingestion.md").write_text(to_markdown(report))
    print(to_markdown(report))
    ok = report["files_loaded"] == report["files_total"]
    ok = ok and report["ocr_cer_max"] is not None and report["ocr_cer_max"] < CER_TARGET
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
