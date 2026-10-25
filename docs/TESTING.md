# Testing strategy

How ContractGuard is tested, and what counts as evidence that a phase is done.
Acceptance targets come from the HLD (§12, §14); this file says how each is checked.

## Principles

- **The LLM is always mocked in tests** (`MockProvider`). No test calls a network service.
- **Deterministic.** No randomness at inference; generators use fixed seeds. The same input gives
  the same output, so tests compare exact values.
- **Behaviour, not implementation.** A test feeds realistic input (a clause, a PDF page) and checks
  the result a reviewer would see (a fact value, a status), not private helpers.
- **Every bug fixed gets a regression test** that fails before the fix.
- **The gold set is evaluation data, never test fixtures for tuning.** Unit tests use small inline
  strings or generated files under `tmp_path`.

## Layers

| Layer | Scope | Tooling | Where |
|---|---|---|---|
| Unit | One module: config loading, duration parsing, regex detectors, policy checks | pytest | `tests/test_<module>.py` |
| Component | One pipeline stage on real files: a generated DOCX/PDF through ingestion + cleaning | pytest + python-docx / PyMuPDF fixtures | `tests/test_<stage>_*.py` |
| Pipeline | `pipeline.run()` on gold contracts with the LLM off | pytest (marked `slow`) | `tests/test_pipeline.py` |
| API | Every FastAPI endpoint, success and error paths | `httpx` / FastAPI `TestClient`, temp SQLite | `tests/api/` |
| End to end | Upload → DONE → report in the UI | Playwright against local backend + Streamlit | `tests/e2e/` (Phase 9) |
| Evaluation | Metrics E1–E8 against targets | scripts in `training/` and `evaluation/` | `evaluation/results/` |

Evaluation scripts are not pass/fail tests: they produce reports. A phase is accepted when its
metric meets the HLD target in the generated report.

## What every stage must cover

- **Normal case** on realistic text.
- **Edge cases** named in the HLD for that stage (e.g. negation within 8 tokens, "including without
  limitation", "thirty (30) business days", DOCX auto-numbering, PDFs under 3 pages).
- **Invalid input**: wrong file type, renamed file, encrypted PDF, empty document, oversize file.
- **Failure paths**: missing Tesseract, LLM timeout/429, ambiguous facts → `NEEDS_REVIEW`.
- **Security-sensitive paths**: filename sanitization, magic-byte checks, secrets never printed or
  logged, full contract text never logged at INFO.

## Quality gates (run before every commit)

```bash
ruff format --check .
ruff check .
mypy                # pydantic plugin; config in pyproject.toml
pytest
```

All four must pass. Results are quoted verbatim in each phase summary.

## Phase acceptance checks

| Phase | Check | Target |
|---|---|---|
| 0 | gates above; `python -m contractguard.cli --help` | all green |
| 1 | `build_gold.py` validates all 8 sources and builds 24 files; two human labellings | 24 files; agreement logged |
| 2 | every gold file → `Document`; OCR CER on scanned gold files | 24/24; CER < 5% |
| 3 | `python evaluation/eval_segmentation.py`: boundary P/R/F1 on 10 annotated contracts (E2; 8 gold now, 2 CUAD pending) | F1 ≥ 0.85 |
| 4 | macro-F1 on combined test set (E1) | ≥ 0.75 |
| 5 | `python evaluation/eval_facts.py`: fact exact-match accuracy on gold (E4); ≥ 25 duration/liability unit tests (`tests/test_durations.py`, `tests/test_facts.py`) | ≥ 85% |
| 6 | violation recall/precision on gold, LLM off (E5); a test per check type and status branch | R ≥ 0.85, P ≥ 0.80 |
| 7 | grounding pass rate; 30-finding rating sheet by 2 raters (E7) | mean ≥ 4.0, 0 hallucinated values |
| 8 | every endpoint tested; upload → DONE for text PDF, scanned PDF, DOCX | all pass |
| 9 | Playwright journeys at desktop and phone widths; accessibility checklist | all pass |
| 10 | E1–E8 report complete; NLP time for a 20-page PDF (E8) | < 30 s |

## Fixtures

- Small DOCX/PDF files are generated inside tests (python-docx, PyMuPDF) so no binary fixtures are
  committed for unit tests.
- Gold files under `evaluation/gold/` are used only by pipeline tests and evaluation scripts.
- Settings are isolated per test (`tests/conftest.py` clears caches and environment overrides).
