# 14 Tests and tooling

Files: `tests/` (22 test files, 312 tests), `tests/conftest.py`, `tests/fakes.py`, `pyproject.toml`;
strategy in [`docs/TESTING.md`](../TESTING.md).

## What

Unit, integration and UI tests run with pytest, plus three static checks: ruff (lint), ruff format
(formatting) and mypy (types).

## Why

Contract review flags are only useful if they are right. Tests pin down every rule that was learned
the hard way (the D23 page-break bug, OCR Roman numerals, "including but not limited to"), so a
later change cannot silently undo it.

## How

| Area | Test files | Examples |
|---|---|---|
| Foundations | `test_config.py`, `test_models.py` | environment overrides, secret hiding, offset maps |
| Ingestion | `test_ingestion.py` | PDFs and DOCX built inside the test; magic bytes; encrypted PDF; fake OCR; one real Tesseract test, skipped if Tesseract is absent |
| Cleaning | `test_cleaner.py` | header removal, the D23 page-break regression, the "(15) days" join |
| Segmentation | `test_segmenter.py` | numbering styles, OCR Roman numerals, fallback, long-clause splits |
| Extraction | `test_durations.py`, `test_facts.py` | number words, business days, negation windows, minimum notice, ambiguity |
| Classification | `test_classifier.py` | thresholds, SLA rule, embedding fallback with a fake embedder, missing artifacts |
| Policy | `test_policy_engine.py`, `test_policy_schema.py`, `test_policy_file.py` | every status path, schema errors, versioned saves, the shipped policy is valid |
| LLM | `test_explainer.py` | grounding failures, invented numbers, retries with a fake clock, cache hits, templates |
| Pipeline and CLI | `test_pipeline.py`, `test_cli.py` | gold files end to end, warnings, exit codes |
| Backend | `test_backend.py`, `test_embedded_backend.py` | every endpoint, bad uploads, models missing, policy versions; when the UI starts the API itself |
| UI | `test_frontend.py` | every page headless with Streamlit `AppTest` against a real backend |
| Scripts | `test_build_gold.py`, `test_inspect_labels.py`, `test_label_agreement.py` | gold building and agreement maths |

**Isolation.** `conftest.py` clears cached settings and patterns and removes environment overrides
before each test. Slow or external pieces are injected: the PDF loader takes an `ocr_fn`, the
explainer takes a provider, a clock and a sleep function, and `fakes.py` supplies a fake classifier
and embedder. The LLM is always mocked in tests.

**Static checks.** ruff rules E, W, F, I, B and UP with a 100-character line limit; mypy with the
Pydantic plugin over `contractguard` and `backend`.

```bash
pytest                    # 312 passed (2026-11-08); 308 of them also inside the Docker image on Python 3.12
ruff check . && ruff format --check .
mypy
```

## Interview notes

- *Unit vs integration tests?* Unit tests check one function with controlled inputs; integration
  tests run several stages together, here the whole pipeline on the gold files and the API with the
  UI on top.
- *How do you test code that calls an LLM?* Dependency injection of a mock provider that can return
  scripted answers or raise errors, and an injected clock so retry waits take no time.
- *What did static typing catch?* 11 errors in Phase 0, such as values that could be `None` being
  used as strings.
- *What is a regression test?* A test added with a bug fix that reproduces the failing case, so the
  bug cannot come back unnoticed.
