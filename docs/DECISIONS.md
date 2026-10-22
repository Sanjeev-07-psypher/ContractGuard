# Design decisions

Choices not fixed by the HLD, recorded as required by HLD §0. Newest last.

| # | Date | Phase | Decision | Reason |
|---|---|---|---|---|
| D1 | 2026-10-22 | 0 | Packaging via `pyproject.toml` (setuptools) with extras `training`, `app`, `ollama`, `dev` instead of two requirements files. | One file; the core install stays free of FastAPI/Streamlit, matching HLD §0.2. |
| D2 | 2026-10-22 | 0 | Env overrides: `CG_` prefix with `__` nesting (e.g. `CG_LLM__RPM=4`), plus the flat names `LLM_PROVIDER`, `LLM_MODEL`, `GEMINI_API_KEY` from `.env.example`. Precedence: env > `.env` > `settings.yaml`. | Lets the Windows Tesseract path and model name be set without editing YAML. |
| D3 | 2026-10-22 | 0 | `llm.model` added to `settings.yaml` (default `null`, set via `LLM_MODEL`); `llm.provider` may also be `none`. `paths` section added for data/uploads/sqlite/models. `policy.policies_dir` added. | HLD §9.1 forbids hard-coding the model; paths must not be hard-coded either (§0.4). |
| D4 | 2026-10-22 | 0 | Use `import pymupdf` (not `fitz`). | PyMuPDF ≥ 1.24 deprecates the `fitz` alias. |
| D5 | 2026-10-22 | 0 | Tooling targets Python 3.11 (`requires-python >= 3.11`, ruff `py311`). | HLD §0.6. |
| D6 | 2026-10-22 | 1 | Gold contracts are authored once as YAML (`evaluation/gold/src/*.yaml`) and `build_gold.py` generates the DOCX, the text PDF (LibreOffice headless export of the DOCX) and the scanned PDF (rendered at 200 DPI, seeded skew/noise/blur, image-only), plus `gold.json`. | Single source of truth; all 24 files are reproducible. |
| D7 | 2026-10-22 | 1 | GC03 uses real Word auto-numbering (`w:numPr`) for its clause numbers; the other seven type numbers as text. | Exercises the DOCX numbering synthesis of HLD §6.1 on at least one gold file. |
| D8 | 2026-10-22 | 1 | DOCX files carry a running header and a "Page X of Y" footer. | The exported PDFs then exercise header/footer and page-number removal (HLD §6.2). |
