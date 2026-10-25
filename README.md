# ContractGuard

AI-assisted contract risk and compliance review: reads a contract (text PDF, scanned PDF or DOCX),
splits it into clauses, classifies them, extracts key facts, checks them against a configurable
policy and explains each flag in plain English.

> ContractGuard produces AI-assisted review flags to support contract reviewers. It is not legal
> advice and does not determine legal validity.

The design is in the HLD (`docs/` / project files). Build progress follows HLD §14:

| Phase | Status |
|---|---|
| 0 Skeleton, config, models, tooling (pytest, ruff, mypy) | done |
| 1 Gold set + label inspection | 8 contracts × 3 formats built; human labelling and the label-inspection run (needs Hugging Face access) still open |
| 2 Ingestion (PDF, OCR, DOCX) + cleaning | done: 24/24 gold files load; OCR CER 1.1% mean (simulated scans), see `evaluation/results/ingestion.md` |
| 3–10 | not started |

## Setup (development)

System tools: Tesseract 5 (`apt install tesseract-ocr`; Windows: UB-Mannheim installer, then set
`CG_OCR__TESSERACT_CMD`) and, only to rebuild the gold set, LibreOffice.


```bash
python3.11 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
python -m contractguard.cli --help
```

Configuration lives in `config/*.yaml` and `policies/*.json`. Copy `.env.example` to `.env` for
secrets and model selection. Any setting can be overridden with `CG_<SECTION>__<KEY>`, for example
`CG_OCR__TESSERACT_CMD="C:\Program Files\Tesseract-OCR\tesseract.exe"`.

## Phase 1 tasks for the team

- Run `pip install -e ".[training]"` then `python training/inspect_labels.py`. It writes
  `docs/labels_ledgar.txt` and `docs/labels_cuad.txt` and checks `config/label_map.yaml`.
- Review and label the gold set: see `evaluation/gold/GUIDELINES.md`.
- Regenerate gold files after editing a source YAML:
  `python evaluation/gold/build_gold.py` (needs LibreOffice for the text PDFs).
