# 09 Pipeline, report and CLI

Files: `contractguard/pipeline.py`, `contractguard/report/builder.py`, `contractguard/cli.py`.

## What

- **`pipeline.py`** runs all stages in order and returns a `Report`.
- **`report/builder.py`** assembles the final `Report`: checklist, counts, warnings, versions,
  timings and the disclaimer.
- **`cli.py`** is the command-line entry point: `contractguard analyze <file>` and
  `contractguard config`.

## Why

One orchestrator means the CLI, the API, the tests and the evaluation scripts all run exactly the
same code path. Loading slow resources once (the classifier, MiniLM, the LLM client) and reusing
them is what makes the API fast after startup.

## How

### `Resources` and `Options`

- `Options`: per-run choices: contract type (or auto), our organisation's name, policy id, whether
  to use the LLM.
- `Resources.load(settings, with_embeddings, with_llm, cache_path)`: loads the embedder (or records
  a warning if it is unavailable), the classifier (raises if missing), the LLM provider and the LLM
  cache. The backend calls this once at startup; the CLI once per run.

### `run(path, options, resources, progress_cb, contract_id, filename)`

| Step | Progress | Work |
|---|---|---|
| EXTRACTING | 5% | `load_document`, then `clean_document` |
| SEGMENTING | 30% | `segment` |
| CLASSIFYING | 45% | `classifier.classify` |
| EVALUATING | 65% | load the policy; our organisation = option, else the policy's default, else the setting; `extract_meta`, `extract_facts`, `PolicyEngine.evaluate` |
| EXPLAINING | 80% | `Explainer.explain_findings` and the executive summary |
| DONE | 100% | `build_report` |

Each stage is timed with `time.perf_counter()` and the timings go into `Report.timings_s`
(`extract`, `segment`, `classify`, `evaluate`, `explain`).

**Failure policy (HLD 16).** Ingestion errors and a missing classifier stop the run with a readable
`ContractGuardError`. A missing embedder, unresolved party roles, or a failing LLM only add
warnings; the report is still produced.

### Report builder

- `clause_checklist`: for each category except OTHER, whether at least one body or exhibit clause
  has it.
- `counts`: `HIGH`, `MEDIUM`, `LOW` count the issues (NON_COMPLIANT and MISSING) by severity; each
  status has its own count; `CLAUSES` counts body and exhibit clauses (D41).
- Warnings from ingestion and the pipeline are merged without duplicates.
- Records `policy_id`, `policy_version`, `pipeline_version`, `generated_at` (UTC), the disclaimer,
  file type, page count, OCR pages and whether the LLM was used.

### CLI

```bash
contractguard analyze contract.pdf --org "ABC Technologies Pvt. Ltd." --no-llm -o report.json
contractguard config        # effective settings, API key shown only as set / not set
```

`analyze` prints the title, type, parties, counts, every flagged finding with its location and
reason, the warnings and the disclaimer. Exit codes: 0 success, 1 a ContractGuard error (printed as
`error [CODE]: message`), 2 file not found.

## Callers and dependencies

Called by the CLI, `backend/jobs.py`, and the evaluation scripts. Calls every `contractguard`
stage.

## Data in and out

In: a file path, `Options`, `Resources`, an optional progress callback. Out: a `Report`.

## Errors and edge cases

- Progress callbacks let the backend show the stage in the UI; the CLI passes none.
- If explanation fails as a whole, the explainer is rebuilt without a provider and templates are
  used, with a warning naming the exception type.

## Configuration

Reads `Settings` through `Resources`; `--org`, `--policy`, `--contract-type`, `--no-llm` override
per run.

## Alternatives considered

- **A workflow framework (Airflow, Prefect)**: built for scheduled batch jobs, far too heavy for a
  six-step function call.
- **Load models inside `run`**: simpler, but every API request would pay seconds of loading.

## Interview notes

- *What is the order of stages?* Ingest and clean, segment, classify, extract metadata and facts,
  evaluate the policy, explain, build the report. Metadata comes after classification because
  governing law is read from the classified governing-law clauses.
- *How fast is it (E8)?* Without the LLM, about 0.2 to 0.3 s per text PDF or DOCX and about 7 s
  per scanned contract (OCR dominates, about 3 s per page) on a CPU. The target was under 30 s for a
  20-page text PDF.
- *What happens if Gemini is down?* Retries with backoff, then template explanations and a warning.
  Statuses do not change.
