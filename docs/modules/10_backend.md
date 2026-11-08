# 10 Backend API

Files: `backend/main.py`, `backend/api/contracts.py`, `backend/api/policies.py`, `backend/jobs.py`,
`backend/tables.py`, `backend/db.py`, `backend/state.py`, `backend/errors.py`.

## What

A FastAPI application under `/api/v1` that accepts uploads, runs analyses in the background one at
a time, stores results in SQLite, and serves reports, clauses and policies to the UI.

## Why

Analysis takes from under a second to over a minute (OCR, LLM calls), which is too long for one
HTTP request. A job queue with status polling keeps the UI responsive. Keeping all NLP in the
`contractguard` package and all HTTP concerns here means either side can change independently.

## How

### Startup (`main.py`)

`create_app` uses FastAPI's lifespan hook to build an `AppState`: settings, a SQLModel engine for
`data/contractguard.db`, the uploads folder, the policies folder, and `Resources.load(...)` (models
loaded once). If loading fails (for example no trained classifier), the API **still starts**:
`/health` reports the reason and uploads return 503 (D43). CORS allows only the Streamlit origin
(D45).

### Endpoints

| Method and path | Purpose | Notes |
|---|---|---|
| `GET /health` | readiness | models, embeddings, Tesseract, LLM provider, version, disclaimer |
| `POST /contracts` | upload | multipart: `file`, `contract_type`, `our_org_name`, `policy_id`, `use_llm`; returns 202 and `contract_id` |
| `GET /contracts` | list | newest first, with counts |
| `GET /contracts/{id}/status` | poll | status, stage, progress, error |
| `GET /contracts/{id}/report` | report | 409 until DONE |
| `GET /contracts/{id}/clauses` | clauses | 409 until DONE |
| `DELETE /contracts/{id}` | delete | removes rows and the uploaded file |
| `GET /policies`, `GET /policies/{id}` | read policies | |
| `PUT /policies/{id}` | edit a policy | schema-validated, versioned |

Interactive documentation is generated automatically at `/docs`.

### Upload checks (D44)

Before queueing: the extension is `.pdf` or `.docx` (415 otherwise), the contract type is known
(422), the policy exists (422), the size is within `limits.max_file_mb` (413), the file is not
empty (422). The filename keeps only letters, digits, `._ -`, the base name only, at most 120
characters. Magic bytes, page and word limits are checked by the pipeline, so a renamed file is
accepted, then FAILED with a readable error.

### Jobs (`jobs.py`)

`run_job` runs in FastAPI's `BackgroundTasks` behind a `threading.Semaphore(1)`: one analysis at a
time, to avoid CPU and memory spikes and to respect LLM rate limits. The progress callback writes
the stage and percentage to the contract row. On success `store_report` saves the whole report as
JSON plus one row per clause and per finding; on failure the row becomes FAILED with the error
message (internal errors show only the exception type, never a stack trace).

### Storage (`tables.py`)

| Table | Holds |
|---|---|
| `contracts` | id, filename, type, status, stage, progress, error, options, policy version, timestamps, `report_json`, `counts_json` |
| `clauses` | one row per clause, for filtering |
| `findings` | one row per finding, with the explanation as JSON |
| `llm_cache` | cached LLM answers (shared with the explainer) |

### Errors (`errors.py`)

Every error response is `{"error_code": ..., "message": ...}`, including request validation errors
(`VALIDATION_ERROR`, 422).

## Callers and dependencies

Called by the Streamlit UI through `frontend/api_client.py`. Uses FastAPI, Uvicorn, SQLModel
(SQLAlchemy), python-multipart and the `contractguard` pipeline.

## Errors and edge cases

- A contract deleted while running: updates find no row and stop quietly.
- Models not loaded: 503 `MODELS_NOT_LOADED` with the reason.
- No authentication in V1 (single user on localhost); the public demo is shared by all visitors.

## Configuration

`paths.sqlite_path`, `paths.uploads_dir`, `limits.*`, `frontend.origin`, plus everything the
pipeline reads.

## Alternatives considered

- **Celery and Redis for jobs**: robust but two more services; one in-process worker is enough for
  a single-user tool.
- **PostgreSQL**: unnecessary for one user; SQLite is a single file with no server.
- **Flask**: no built-in validation or OpenAPI docs; FastAPI generates both from type hints.

## Interview notes

- *Why 202 Accepted?* The request is accepted for processing that has not finished; the client
  polls the status endpoint.
- *How do you protect against malicious uploads?* Extension and magic-byte checks, size, page and
  word limits, sanitised filenames, files stored under a random id, encrypted PDFs rejected.
- *Why store the report twice (JSON and rows)?* The JSON is what the UI shows in one read; the rows
  allow filtering and future queries across contracts.
- *How is it tested?* `TestClient` and a fake classifier with the mock LLM, including the failure
  paths (bad type, oversized file, unknown policy, models not loaded).
